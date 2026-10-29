"""Check the live local image endpoint using generated non-personal images only."""
import io
import json
from pathlib import Path

import httpx
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
base="http://127.0.0.1:8000"
headers={"X-Local-Capture":"quality-test","Content-Type":"image/jpeg"}
with httpx.Client(timeout=20) as client:
    results=[]
    for name,content,expected,reason in [
        ("invalid-image",b"not an image",422,"invalid_image"),
        ("oversized-upload",b"x"*2_000_001,413,None),
    ]:
        response=client.post(base+"/api/diagnostics/face",headers=headers,content=content)
        assert response.status_code==expected,(name,response.status_code)
        if reason:
            assert response.json()["reason"]==reason
        results.append({"case":name,"status":response.status_code,"passed":True})
    buffer=io.BytesIO()
    Image.new("RGB",(2001,2001),"white").save(buffer,format="PNG")
    response=client.post(base+"/api/diagnostics/face",headers=headers,content=buffer.getvalue())
    assert response.status_code==422 and response.json()["reason"]=="invalid_image_dimensions"
    results.append({"case":"oversized-dimensions","status":response.status_code,"passed":True})
    assert client.get(base+"/health/live").status_code==200
    assert client.get(base+"/api/admin/employees").status_code==401
    results.append({"case":"live-after-rejections","passed":True})
    report={"target":base,"actual_model_endpoint":True,"generated_images_only":True,"results":results,"images_saved":False}
    (ROOT/"evidence/m1/capture-api-check.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("Live capture endpoint rejected invalid image, oversized bytes and dimensions; server stayed alive")
