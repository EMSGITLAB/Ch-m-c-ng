import csv
import io
import unicodedata
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from .auth import Admin, Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import lock_calendar
from .models import AuditLog, Employee, FaceCollection, FaceTemplate, ImportedFacePhoto

router=APIRouter(prefix="/api/admin/employees",tags=["employees"])


class EmployeeInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    code:str=Field(min_length=1,max_length=40,pattern=r"^[A-Za-z0-9_-]+$")
    name:str=Field(min_length=2,max_length=160)
    department:str=Field(default="",max_length=120)
    active:bool=True

    @field_validator("name","department",mode="before")
    @classmethod
    def clean_text(cls,value):
        if isinstance(value,str):
            value=unicodedata.normalize("NFC",value.strip())
            if any(unicodedata.category(char).startswith("C") for char in value):
                raise ValueError("Không dùng ký tự điều khiển.")
        return value

    @field_validator("code",mode="before")
    @classmethod
    def clean_code(cls,value):
        return value.strip().upper() if isinstance(value,str) else value


class EmployeePatch(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str|None=Field(default=None,min_length=2,max_length=160)
    department:str|None=Field(default=None,max_length=120)
    active:bool|None=None

    @field_validator("name","department",mode="before")
    @classmethod
    def clean_text(cls,value):
        return EmployeeInput.clean_text(value)


def public_employee(employee,templates=0,collections=0,imported_photos=0,photo_id=None):
    return {"id":employee.id,"code":employee.code,"name":employee.name,"department":employee.department,
            "active":employee.active,"deleted_at":employee.deleted_at.isoformat() if employee.deleted_at else None,"template_count":templates,"collection_count":collections,"imported_photo_count":imported_photos,
            "profile_photo_url":f"/api/admin/imported-face-photos/{photo_id}/image" if photo_id else None,
            "created_at":employee.created_at.isoformat()}


@router.get("/departments")
def departments(db:Db,user:Admin):
    return {"items":db.scalars(select(Employee.department).where(Employee.department!="",Employee.deleted_at.is_(None))
                              .distinct().order_by(Employee.department)).all()}


@router.get("")
def list_employees(db:Db,user:Admin,q:str="",active:bool|None=None,offset:int=0,limit:int=30,deleted:bool=False):
    if offset<0 or not 1<=limit<=100 or len(q)>160:
        raise HTTPException(422,"Phạm vi tra cứu không hợp lệ.")
    filters=[Employee.deleted_at.is_not(None) if deleted else Employee.deleted_at.is_(None)]
    if active is not None:
        filters.append(Employee.active==active)
    if q.strip():
        search="%"+q.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        filters.append(or_(Employee.code.ilike(search,escape="\\"),Employee.name.ilike(search,escape="\\"),Employee.department.ilike(search,escape="\\")))
    count=db.scalar(select(func.count()).select_from(Employee).where(*filters))
    template_count=select(func.count()).where(FaceTemplate.employee_id==Employee.id).correlate(Employee).scalar_subquery()
    collection_count=select(func.count()).where(FaceCollection.employee_id==Employee.id,FaceCollection.status=="complete").correlate(Employee).scalar_subquery()
    photo_count=select(func.count()).where(ImportedFacePhoto.employee_id==Employee.id).correlate(Employee).scalar_subquery()
    photo_id=(select(ImportedFacePhoto.id).where(ImportedFacePhoto.employee_id==Employee.id,
        ImportedFacePhoto.biometric_revision==Employee.biometric_revision)
        .order_by(ImportedFacePhoto.created_at.desc(),ImportedFacePhoto.id.desc()).limit(1).correlate(Employee).scalar_subquery())
    rows=db.execute(select(Employee,template_count,collection_count,photo_count,photo_id).where(*filters).order_by(Employee.code).offset(offset).limit(limit)).all()
    return {"items":[public_employee(employee,templates,collections,photos,portrait) for employee,templates,collections,photos,portrait in rows],"total":count,"offset":offset,"limit":limit}


@router.post("",status_code=201)
def create_employee(payload:EmployeeInput,db:Db,user:MutationAdmin):
    employee=Employee(**payload.model_dump())
    db.add(employee)
    try:
        db.flush()
        db.add(AuditLog(action="employee_create",entity_id=employee.id,details={"code":employee.code}))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,"Mã nhân viên đã tồn tại.") from error
    return public_employee(employee)


@router.patch("/{employee_id}")
def update_employee(employee_id:str,payload:EmployeePatch,db:Db,user:MutationAdmin):
    lock_calendar(db)
    employee=db.get(Employee,employee_id)
    if employee is None:
        raise HTTPException(404,"Không tìm thấy nhân viên.")
    lock_employee(db,employee_id)
    db.refresh(employee)
    if employee.deleted_at is not None:
        raise HTTPException(409,"Hồ sơ đã xóa, chỉ giữ để tra cứu lịch sử chấm công.")
    changes=payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422,"Không để trống giá trị trường đang cập nhật.")
    before={key:getattr(employee,key) for key in changes}
    for key,value in changes.items():
        setattr(employee,key,value)
    db.add(AuditLog(action="employee_update",entity_id=employee.id,details={"before":before,"after":changes}))
    db.commit()
    count=db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id==employee.id))
    return public_employee(employee,count)


@router.delete("/{employee_id}")
def delete_employee(employee_id:str,db:Db,user:MutationAdmin):
    lock_calendar(db)
    employee=db.get(Employee,employee_id)
    if employee is None:
        raise HTTPException(404,"Không tìm thấy nhân viên.")
    lock_employee(db,employee_id)
    db.refresh(employee)
    if employee.deleted_at is None:
        employee.active=False
        employee.deleted_at=datetime.now(UTC)
        employee.biometric_revision+=1
        db.add(AuditLog(action="employee_delete",entity_id=employee.id,
                        details={"soft_delete":True,"attendance_preserved":True}))
    db.commit()
    return {"deleted":True,"employee_id":employee.id,"attendance_preserved":True}


@router.post("/import-csv",status_code=201)
async def import_employees(request:Request,db:Db,user:MutationAdmin):
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>256_000:
            raise HTTPException(413,"CSV tối đa 256 KB và 100 nhân viên.")
    try:
        reader=csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        fields=reader.fieldnames or []
        if len(set(fields))!=len(fields) or not {"code","name"}<=set(fields) or set(fields)-{"code","name","department"}:
            raise HTTPException(422,"CSV cần cột code,name; department là tùy chọn. Không dùng cột khác.")
        parsed=[]
        codes=set()
        errors=[]
        for number,row in enumerate(reader,start=2):
            if number>101:
                raise HTTPException(413,"Mỗi lần nhập tối đa 100 nhân viên.")
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Số cột không khớp.")
                item=EmployeeInput.model_validate(row)
                if item.code in codes:
                    raise ValueError("Mã trùng trong tệp.")
                codes.add(item.code)
                parsed.append(item)
            except (ValidationError,ValueError):
                errors.append({"row":number,"message":"Dữ liệu thiếu, mã trùng hoặc giá trị không hợp lệ."})
        if errors:
            raise HTTPException(422,{"message":"Chưa nhập dòng nào; sửa các dòng lỗi rồi thử lại.","rows":errors})
    except (UnicodeDecodeError,csv.Error) as error:
        raise HTTPException(422,"Tệp cần là CSV UTF-8 hợp lệ.") from error
    if not parsed:
        raise HTTPException(422,"CSV không có nhân viên.")
    existing=db.scalars(select(Employee.code).where(func.upper(Employee.code).in_(codes))).all()
    if existing:
        raise HTTPException(409,{"message":"Có mã đã tồn tại; chưa nhập dòng nào.","codes":list(existing)})
    db.add_all(Employee(**item.model_dump()) for item in parsed)
    db.add(AuditLog(action="employee_import",details={"count":len(parsed)}))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,"Mã nhân viên bị trùng; chưa nhập dòng nào.") from error
    return {"imported":len(parsed)}
