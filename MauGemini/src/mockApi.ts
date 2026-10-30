// Local in-memory and localStorage API mock for standalone React deployment
// Implements all backend routes faithfully according to Vietnamese business specs

interface Employee {
  id: string;
  code: string;
  name: string;
  department: string;
  active: boolean;
  template_count: number;
  collection_count?: number;
  imported_photo_count?: number;
  profile_photo_url?: string | null;
}

interface Device {
  id: string;
  name: string;
  direction: 'in' | 'out';
  active: boolean;
  paired: boolean;
  last_seen_at: string | null;
  pairing_code?: string;
  expires_at?: string;
}

interface Break {
  start: string;
  end: string;
  paid: boolean;
}

interface Shift {
  id: string;
  family_id: string;
  name: string;
  start: string;
  end: string;
  breaks: Break[];
  late_grace_minutes: number;
  early_grace_minutes: number;
  capture_before_minutes: number;
  capture_after_minutes: number;
  revision: number;
  active: boolean;
  overnight: boolean;
  timezone: string;
  expected_work_minutes: number;
}

interface Assignment {
  id: string;
  employee_id: string;
  employee_code: string;
  employee_name: string;
  work_date: string;
  shift: Shift;
  cancelled: boolean;
  cancel_reason: string | null;
}

interface PunchEntry {
  id: string;
  employee_id: string;
  employee_code: string;
  employee_name: string;
  direction: 'in' | 'out';
  occurred_at: string;
  voided: boolean;
  kind: string;
  reason?: string;
  revoked_at?: string | null;
  revoke_reason?: string | null;
  created_at: string;
}

interface Snapshot {
  revision: number;
  created_at: string;
  reason: string;
  summary: { row_count: number; worked_seconds: number };
}

interface Period {
  month: string;
  status: string;
  revision: number;
  snapshots: Snapshot[];
}

interface RecognitionSession {
  request_id: string;
  state: 'pending' | 'verified' | 'rejected' | 'used';
  next_frame_index: number;
  capture_nonce: string;
  needs_supervisor: boolean;
  employee_code: string;
  employee_name: string;
  receipt?: unknown;
}

const STORAGE_KEY = 'chamcong_local_db_v2';

function getDefaultData() {
  const defaultEmployees: Employee[] = [
    { id: 'emp-01', code: 'NV001', name: 'Nguyễn Văn An', department: 'Công nghệ thông tin', active: true, template_count: 5, collection_count: 2, imported_photo_count: 3 },
    { id: 'emp-02', code: 'NV002', name: 'Trần Thị Bích', department: 'Kế toán tài chính', active: true, template_count: 5, collection_count: 2, imported_photo_count: 2 },
    { id: 'emp-03', code: 'NV003', name: 'Lê Hoàng Cường', department: 'Kinh doanh', active: true, template_count: 4, collection_count: 1, imported_photo_count: 1 },
    { id: 'emp-04', code: 'NV004', name: 'Phạm Thị Dung', department: 'Nhân sự', active: true, template_count: 5, collection_count: 2, imported_photo_count: 2 },
    { id: 'emp-05', code: 'NV005', name: 'Vũ Đức Em', department: 'Vận hành kho', active: true, template_count: 4, collection_count: 1, imported_photo_count: 1 },
    { id: 'emp-06', code: 'NV006', name: 'Đỗ Thị Giang', department: 'Kế toán tài chính', active: true, template_count: 5, collection_count: 2, imported_photo_count: 2 },
    { id: 'emp-07', code: 'NV007', name: 'Bùi Quang Hùng', department: 'Công nghệ thông tin', active: true, template_count: 5, collection_count: 2, imported_photo_count: 3 },
    { id: 'emp-08', code: 'NV008', name: 'Hoàng Mai Lan', department: 'Kinh doanh', active: true, template_count: 4, collection_count: 1, imported_photo_count: 1 },
    { id: 'emp-09', code: 'NV009', name: 'Ngô Quốc Nam', department: 'Vận hành kho', active: true, template_count: 3, collection_count: 1, imported_photo_count: 0 },
    { id: 'emp-10', code: 'NV010', name: 'Đặng Thảo Vy', department: 'Nhân sự', active: false, template_count: 0, collection_count: 0, imported_photo_count: 0 },
  ];

  const defaultDevices: Device[] = [
    { id: 'dev-01', name: 'Camera Cửa Chính (Vào)', direction: 'in', active: true, paired: true, last_seen_at: new Date().toISOString() },
    { id: 'dev-02', name: 'Camera Cửa Sau (Ra)', direction: 'out', active: true, paired: false, last_seen_at: null, pairing_code: '83921045', expires_at: new Date(Date.now() + 86400000).toISOString() },
  ];

  const defaultShifts: Shift[] = [
    {
      id: 'shift-01',
      family_id: 'fam-01',
      name: 'Ca hành chính',
      start: '08:00',
      end: '17:00',
      breaks: [{ start: '12:00', end: '13:00', paid: false }],
      late_grace_minutes: 15,
      early_grace_minutes: 15,
      capture_before_minutes: 120,
      capture_after_minutes: 120,
      revision: 1,
      active: true,
      overnight: false,
      timezone: 'Asia/Ho_Chi_Minh',
      expected_work_minutes: 480,
    },
    {
      id: 'shift-02',
      family_id: 'fam-02',
      name: 'Ca sáng (Sản xuất)',
      start: '06:00',
      end: '14:00',
      breaks: [{ start: '11:00', end: '11:30', paid: true }],
      late_grace_minutes: 10,
      early_grace_minutes: 10,
      capture_before_minutes: 60,
      capture_after_minutes: 60,
      revision: 1,
      active: true,
      overnight: false,
      timezone: 'Asia/Ho_Chi_Minh',
      expected_work_minutes: 480,
    },
    {
      id: 'shift-03',
      family_id: 'fam-03',
      name: 'Ca tối (Sản xuất)',
      start: '14:00',
      end: '22:00',
      breaks: [{ start: '18:00', end: '18:30', paid: true }],
      late_grace_minutes: 10,
      early_grace_minutes: 10,
      capture_before_minutes: 60,
      capture_after_minutes: 60,
      revision: 1,
      active: true,
      overnight: false,
      timezone: 'Asia/Ho_Chi_Minh',
      expected_work_minutes: 480,
    },
  ];

  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

  const defaultAssignments: Assignment[] = defaultEmployees.filter(e => e.active).map((emp, idx) => ({
    id: `asg-${idx + 1}`,
    employee_id: emp.id,
    employee_code: emp.code,
    employee_name: emp.name,
    work_date: today,
    shift: defaultShifts[0],
    cancelled: false,
    cancel_reason: null,
  }));

  const defaultPunches: PunchEntry[] = [
    {
      id: 'punch-01',
      employee_id: 'emp-01',
      employee_code: 'NV001',
      employee_name: 'Nguyễn Văn An',
      direction: 'in',
      occurred_at: `${today}T07:54:12+07:00`,
      voided: false,
      kind: 'kiosk',
      created_at: `${today}T07:54:12+07:00`,
    },
    {
      id: 'punch-02',
      employee_id: 'emp-02',
      employee_code: 'NV002',
      employee_name: 'Trần Thị Bích',
      direction: 'in',
      occurred_at: `${today}T08:04:30+07:00`,
      voided: false,
      kind: 'kiosk',
      created_at: `${today}T08:04:30+07:00`,
    },
    {
      id: 'punch-03',
      employee_id: 'emp-03',
      employee_code: 'NV003',
      employee_name: 'Lê Hoàng Cường',
      direction: 'in',
      occurred_at: `${today}T08:18:22+07:00`,
      voided: false,
      kind: 'kiosk',
      created_at: `${today}T08:18:22+07:00`,
    },
    {
      id: 'punch-04',
      employee_id: 'emp-01',
      employee_code: 'NV001',
      employee_name: 'Nguyễn Văn An',
      direction: 'in',
      occurred_at: `${yesterday}T07:58:00+07:00`,
      voided: false,
      kind: 'kiosk',
      created_at: `${yesterday}T07:58:00+07:00`,
    },
    {
      id: 'punch-05',
      employee_id: 'emp-01',
      employee_code: 'NV001',
      employee_name: 'Nguyễn Văn An',
      direction: 'out',
      occurred_at: `${yesterday}T17:05:00+07:00`,
      voided: false,
      kind: 'kiosk',
      created_at: `${yesterday}T17:05:00+07:00`,
    },
  ];

  return {
    employees: defaultEmployees,
    devices: defaultDevices,
    shifts: defaultShifts,
    assignments: defaultAssignments,
    punches: defaultPunches,
    adjustments: [] as PunchEntry[],
    currentDeviceId: 'dev-01',
    periods: [
      {
        month: today.slice(0, 7),
        status: 'open',
        revision: 1,
        snapshots: [] as Snapshot[],
      },
    ] as Period[],
  };
}

class MockStore {
  data: ReturnType<typeof getDefaultData>;
  sessions = new Map<string, RecognitionSession>();

  constructor() {
    this.data = this.load();
  }

  load() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved);
    } catch {
      // fallback
    }
    const fresh = getDefaultData();
    this.save(fresh);
    return fresh;
  }

  save(data = this.data) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // fallback
    }
  }
}

export function initMockApi() {
  const store = new MockStore();
  const originalFetch = typeof window !== 'undefined' && window.fetch ? window.fetch.bind(window) : fetch.bind(globalThis);
  const customFetch = async function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(urlStr, window.location.origin);
    const method = (init?.method || 'GET').toUpperCase();

    // Check if it's an API route
    if (!url.pathname.startsWith('/api/') && url.pathname !== '/health') {
      return originalFetch(input, init);
    }

    // Helper to return json
    const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers },
      });

    const error = (detail: string | object, status = 400) =>
      new Response(JSON.stringify({ detail }), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });

    let bodyData: any = null;
    if (init?.body && typeof init.body === 'string') {
      try {
        bodyData = JSON.parse(init.body);
      } catch {
        bodyData = init.body;
      }
    }

    try {
      // 1. System Status
      if (url.pathname === '/api/system/status' || url.pathname === '/health') {
        const now = new Date();
        return json({
          server_time: now.toISOString(),
          timezone: 'Asia/Ho_Chi_Minh',
          recognition_ready: true,
          attendance_enabled: true,
          attendance_mode: 'functional_trial',
          pilot_people: store.data.employees.filter(e => e.active).length,
          pilot_scope: 'all',
          capture_max_edge: 1280,
          message: 'Máy chủ local hoạt động bình thường · Sẵn sàng ghi công',
          version: '0.2.0',
        });
      }

      // 2. Auth
      if (url.pathname === '/api/auth/session') {
        return json({ username: 'admin', csrf_token: 'mock-csrf-token-12345' });
      }
      if (url.pathname === '/api/auth/setup') {
        return json({ requires_setup: false, local_setup_allowed: true });
      }
      if (url.pathname === '/api/auth/login') {
        return json({ username: 'admin', csrf_token: 'mock-csrf-token-12345' });
      }
      if (url.pathname === '/api/auth/logout') {
        return json({ success: true });
      }

      // 3. Kiosk Device (Current client pairing)
      if (url.pathname === '/api/kiosk/device') {
        const device = store.data.devices.find(d => d.id === store.data.currentDeviceId && d.paired);
        if (!device) return error('Chưa ghép thiết bị', 401);
        if ((method === 'PATCH' || method === 'POST') && bodyData?.direction) {
          device.direction = bodyData.direction;
          store.save();
        }
        return json(device);
      }
      if (url.pathname === '/api/kiosk/pair') {
        const code = bodyData?.code;
        const target = store.data.devices.find(d => d.pairing_code === code);
        if (!target) {
          // If code is 12345678 or any 8 digit code, pair device 1 or create one
          const dev = store.data.devices[0] || {
            id: 'dev-01',
            name: 'Camera Cửa Chính',
            direction: 'in',
            active: true,
            paired: true,
            last_seen_at: new Date().toISOString(),
          };
          dev.paired = true;
          store.data.currentDeviceId = dev.id;
          store.save();
          return json(dev);
        }
        target.paired = true;
        store.data.currentDeviceId = target.id;
        store.save();
        return json(target);
      }

      // 4. Admin Devices
      if (url.pathname === '/api/admin/devices') {
        if (method === 'GET') {
          return json({ items: store.data.devices });
        }
        if (method === 'POST') {
          const newCode = String(Math.floor(10000000 + Math.random() * 90000000));
          const newDev: Device = {
            id: `dev-${Date.now().toString(36)}`,
            name: bodyData?.name || 'Điểm chấm công mới',
            direction: bodyData?.direction === 'out' ? 'out' : 'in',
            active: true,
            paired: false,
            last_seen_at: null,
            pairing_code: newCode,
            expires_at: new Date(Date.now() + 86400000).toISOString(),
          };
          store.data.devices.unshift(newDev);
          store.save();
          return json({ device: newDev, pairing_code: newCode, expires_at: newDev.expires_at });
        }
      }

      const matchDevPairing = url.pathname.match(/^\/api\/admin\/devices\/([^/]+)\/pairing$/);
      if (matchDevPairing && method === 'POST') {
        const devId = matchDevPairing[1];
        const dev = store.data.devices.find(d => d.id === devId);
        if (!dev) return error('Không tìm thấy thiết bị', 404);
        const code = String(Math.floor(10000000 + Math.random() * 90000000));
        dev.pairing_code = code;
        dev.expires_at = new Date(Date.now() + 86400000).toISOString();
        store.save();
        return json({ device: dev, pairing_code: code, expires_at: dev.expires_at });
      }

      const matchDevRevoke = url.pathname.match(/^\/api\/admin\/devices\/([^/]+)\/revoke$/);
      if (matchDevRevoke && method === 'POST') {
        const devId = matchDevRevoke[1];
        const dev = store.data.devices.find(d => d.id === devId);
        if (!dev) return error('Không tìm thấy thiết bị', 404);
        dev.paired = false;
        dev.pairing_code = undefined;
        store.save();
        return json(dev);
      }

      // 5. Admin Employees
      if (url.pathname === '/api/admin/employees') {
        if (method === 'GET') {
          const q = (url.searchParams.get('q') || '').trim().toLowerCase();
          const activeParam = url.searchParams.get('active');
          const offset = parseInt(url.searchParams.get('offset') || '0', 10);
          const limit = parseInt(url.searchParams.get('limit') || '30', 10);

          let filtered = store.data.employees;
          if (q) {
            filtered = filtered.filter(
              e => e.name.toLowerCase().includes(q) || e.code.toLowerCase().includes(q) || e.department.toLowerCase().includes(q)
            );
          }
          if (activeParam === 'true') filtered = filtered.filter(e => e.active);
          else if (activeParam === 'false') filtered = filtered.filter(e => !e.active);

          const items = filtered.slice(offset, offset + limit);
          return json({
            items,
            total: filtered.length,
            offset,
            limit,
          });
        }
        if (method === 'POST') {
          const code = bodyData?.code?.trim();
          const name = bodyData?.name?.trim();
          const department = bodyData?.department?.trim() || 'Chung';
          const active = bodyData?.active !== false;

          if (!code || !name) return error('Mã và tên nhân viên là bắt buộc', 400);
          if (store.data.employees.some(e => e.code.toLowerCase() === code.toLowerCase())) {
            return error(`Mã nhân viên "${code}" đã tồn tại trên hệ thống.`, 409);
          }

          const newEmp: Employee = {
            id: `emp-${Date.now().toString(36)}`,
            code,
            name,
            department,
            active,
            template_count: 0,
            collection_count: 0,
            imported_photo_count: 0,
          };
          store.data.employees.unshift(newEmp);
          store.save();
          return json(newEmp);
        }
      }

      const matchEmpUpdate = url.pathname.match(/^\/api\/admin\/employees\/([^/]+)$/);
      if (matchEmpUpdate && method === 'PUT') {
        const empId = matchEmpUpdate[1];
        const emp = store.data.employees.find(e => e.id === empId);
        if (!emp) return error('Không tìm thấy nhân viên', 404);
        if (bodyData.name) emp.name = bodyData.name.trim();
        if (bodyData.code) emp.code = bodyData.code.trim();
        if (bodyData.department) emp.department = bodyData.department.trim();
        if (typeof bodyData.active === 'boolean') emp.active = bodyData.active;
        store.save();
        return json(emp);
      }

      // Employee biometrics and collections
      const matchEmpCollections = url.pathname.match(/^\/api\/admin\/employees\/([^/]+)\/collections$/);
      if (matchEmpCollections) {
        const empId = matchEmpCollections[1];
        if (method === 'GET') {
          return json({
            items: [
              {
                id: `col-${empId}-1`,
                purpose: 'enrollment',
                status: 'completed',
                sample_count: 5,
                expires_at: new Date(Date.now() + 3600000).toISOString(),
                created_at: new Date(Date.now() - 86400000).toISOString(),
                operational_enrollment: true,
                guidance_protocol: 'pose_5',
                next_instruction: null,
              },
            ],
          });
        }
        if (method === 'POST') {
          const colId = `col-${Date.now().toString(36)}`;
          return json({
            id: colId,
            purpose: bodyData?.purpose || 'enrollment',
            status: 'in_progress',
            sample_count: 0,
            expires_at: new Date(Date.now() + 3600000).toISOString(),
            created_at: new Date().toISOString(),
            operational_enrollment: false,
            guidance_protocol: 'standard',
            next_instruction: {
              position: 1,
              pose: 'front',
              title: 'Nhìn thẳng',
              text: 'Giữ đầu ngay ngắn và nhìn thẳng vào camera.',
              arrow: 'none',
            },
          });
        }
      }

      const matchColSample = url.pathname.match(/^\/api\/admin\/employees\/[^/]+\/collections\/([^/]+)\/samples$/);
      if (matchColSample && method === 'POST') {
        return json({
          accepted: true,
          feedback: 'Ảnh đạt chất lượng tốt.',
          next_instruction: {
            position: 2,
            pose: 'left',
            title: 'Nghiêng trái nhẹ',
            text: 'Nghiêng mặt sang trái khoảng 15 độ.',
            arrow: 'left',
          },
        });
      }

      const matchColFinalize = url.pathname.match(/^\/api\/admin\/employees\/([^/]+)\/collections\/[^/]+\/finalize$/);
      if (matchColFinalize && method === 'POST') {
        const emp = store.data.employees.find(e => e.id === matchColFinalize[1]);
        if (emp) {
          emp.template_count = Math.max(emp.template_count, 5);
          emp.collection_count = (emp.collection_count || 0) + 1;
          store.save();
        }
        return json({ status: 'completed', message: 'Đã hoàn tất bộ ảnh mẫu đăng ký.' });
      }

      const matchEmpBiometrics = url.pathname.match(/^\/api\/admin\/employees\/([^/]+)\/biometrics$/);
      if (matchEmpBiometrics && method === 'GET') {
        return json({
          revision: 1,
          active: true,
          current_model_id: 'sface-v1',
          imported_photos: 2,
          templates_by_model: [{ model_id: 'sface-v1', count: 5 }],
          collections_by_model: [{ model_id: 'sface-v1', collections: 2, samples: 10 }],
        });
      }

      if (url.pathname === '/api/admin/imported-face-photos') {
        return json({ items: [{ id: 'photo-1', accepted: true, feedback: 'Ảnh rõ nét' }] });
      }
      if (url.pathname === '/api/admin/imported-face-photos/probe') {
        const emp = store.data.employees[0];
        return json({
          reference_count: 5,
          message: 'Đã so sánh thành công với các khuôn mặt tham chiếu.',
          candidates: emp
            ? [
                {
                  employee_id: emp.id,
                  employee_code: emp.code,
                  employee_name: emp.name,
                  cosine: 0.88,
                  same_reference_file: false,
                },
              ]
            : [],
        });
      }

      // 6. Shifts
      if (url.pathname === '/api/admin/shifts') {
        if (method === 'GET') {
          const includeArchived = url.searchParams.get('include_archived') === 'true';
          const items = includeArchived ? store.data.shifts : store.data.shifts.filter(s => s.active);
          return json({ items });
        }
        if (method === 'POST') {
          const newShift: Shift = {
            id: `shift-${Date.now().toString(36)}`,
            family_id: `fam-${Date.now().toString(36)}`,
            name: bodyData.name,
            start: bodyData.start,
            end: bodyData.end,
            breaks: bodyData.breaks || [],
            late_grace_minutes: bodyData.late_grace_minutes || 0,
            early_grace_minutes: bodyData.early_grace_minutes || 0,
            capture_before_minutes: bodyData.capture_before_minutes || 120,
            capture_after_minutes: bodyData.capture_after_minutes || 120,
            revision: 1,
            active: true,
            overnight: bodyData.start > bodyData.end,
            timezone: 'Asia/Ho_Chi_Minh',
            expected_work_minutes: 480,
          };
          store.data.shifts.unshift(newShift);
          store.save();
          return json(newShift);
        }
      }

      const matchShiftArchive = url.pathname.match(/^\/api\/admin\/shifts\/([^/]+)\/archive$/);
      if (matchShiftArchive && method === 'POST') {
        const s = store.data.shifts.find(x => x.id === matchShiftArchive[1]);
        if (s) {
          s.active = false;
          store.save();
        }
        return json({ success: true });
      }

      // Shift assignments
      if (url.pathname === '/api/admin/shifts/assignments') {
        if (method === 'GET') {
          const includeCancelled = url.searchParams.get('include_cancelled') === 'true';
          const items = includeCancelled ? store.data.assignments : store.data.assignments.filter(a => !a.cancelled);
          return json({ items, has_more: false });
        }
        if (method === 'POST') {
          const shift = store.data.shifts.find(s => s.id === bodyData.shift_id) || store.data.shifts[0];
          const empIds: string[] = bodyData.employee_ids || [];
          const from = bodyData.date_from;
          const to = bodyData.date_to;
          const newItems: Assignment[] = [];

          // Generate for each employee
          for (const empId of empIds) {
            const emp = store.data.employees.find(e => e.id === empId);
            if (!emp) continue;
            newItems.push({
              id: `asg-${Date.now().toString(36)}-${emp.code}`,
              employee_id: emp.id,
              employee_code: emp.code,
              employee_name: emp.name,
              work_date: from || new Date().toISOString().slice(0, 10),
              shift,
              cancelled: false,
              cancel_reason: null,
            });
          }
          store.data.assignments.push(...newItems);
          store.save();
          return json({ count: newItems.length });
        }
      }

      const matchCancelAssignment = url.pathname.match(/^\/api\/admin\/shifts\/assignments\/([^/]+)\/cancel$/);
      if (matchCancelAssignment && method === 'POST') {
        const asg = store.data.assignments.find(a => a.id === matchCancelAssignment[1]);
        if (asg) {
          asg.cancelled = true;
          asg.cancel_reason = bodyData?.reason || 'Hủy phân ca';
          store.save();
        }
        return json({ success: true });
      }

      // 7. Timesheets & Timekeeping
      if (url.pathname === '/api/admin/timesheets/preview') {
        const dateFrom = url.searchParams.get('date_from') || new Date().toISOString().slice(0, 10);
        const dateTo = url.searchParams.get('date_to') || new Date().toISOString().slice(0, 10);
        const empId = url.searchParams.get('employee_id');

        let emps = store.data.employees.filter(e => e.active);
        if (empId) emps = emps.filter(e => e.id === empId);

        const rows: any[] = [];
        let totalWorkedSeconds = 0;
        let lateCount = 0;
        let earlyCount = 0;

        for (const emp of emps) {
          const asg = store.data.assignments.find(a => a.employee_id === emp.id && !a.cancelled) || {
            id: `asg-def-${emp.id}`,
            employee_id: emp.id,
            employee_code: emp.code,
            employee_name: emp.name,
            work_date: dateFrom,
            shift: store.data.shifts[0],
            cancelled: false,
            cancel_reason: null,
          };

          const empPunches = store.data.punches
            .filter(p => p.employee_id === emp.id && !p.voided)
            .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));

          const firstIn = empPunches.find(p => p.direction === 'in')?.occurred_at || null;
          const lastOut = [...empPunches].reverse().find(p => p.direction === 'out')?.occurred_at || null;

          let workedSeconds: number | null = null;
          let isLate = false;
          let lateSeconds: number | null = null;

          if (firstIn && lastOut) {
            const inTime = new Date(firstIn).getTime();
            const outTime = new Date(lastOut).getTime();
            workedSeconds = Math.max(0, Math.floor((outTime - inTime) / 1000) - 3600); // minus 1h break
            totalWorkedSeconds += workedSeconds;
          } else if (firstIn) {
            workedSeconds = 14400; // 4 hours
            totalWorkedSeconds += workedSeconds;
          }

          if (firstIn) {
            const inHour = new Date(firstIn).getHours();
            const inMinute = new Date(firstIn).getMinutes();
            if (inHour > 8 || (inHour === 8 && inMinute > 15)) {
              isLate = true;
              lateCount++;
              lateSeconds = ((inHour - 8) * 60 + inMinute) * 60;
            }
          }

          rows.push({
            assignment_id: asg.id,
            employee_code: emp.code,
            employee_name: emp.name,
            work_date: dateFrom,
            timezone: 'Asia/Ho_Chi_Minh',
            shift: {
              name: asg.shift.name,
              revision: asg.shift.revision,
              start: asg.shift.start,
              end: asg.shift.end,
              overnight: asg.shift.overnight,
            },
            status: firstIn && lastOut ? 'complete' : firstIn ? 'in_progress' : 'needs_review',
            exceptions: !firstIn ? ['missing_in'] : !lastOut ? ['missing_out'] : [],
            first_in: firstIn,
            last_out: lastOut,
            worked_seconds: workedSeconds,
            confirmed_seconds: workedSeconds || 0,
            expected_seconds: 28800,
            presence_seconds: workedSeconds ? workedSeconds + 3600 : 0,
            unpaid_break_seconds: 3600,
            paid_break_credit_seconds: 0,
            outside_shift_seconds: 0,
            late_seconds: lateSeconds,
            early_seconds: null,
            is_late: isLate,
            is_early: false,
            events: empPunches.map(p => ({ id: p.id, direction: p.direction, at: p.occurred_at, source: p.kind })),
          });
        }

        return json({
          source_digest: 'digest-v2',
          finalized: false,
          as_of: new Date().toISOString(),
          calculation_version: '2.0.0',
          rows,
          offset: 0,
          limit: 100,
          has_more: false,
          summary: {
            row_count: rows.length,
            status_counts: { complete: rows.filter(r => r.status === 'complete').length, in_progress: rows.filter(r => r.status === 'in_progress').length },
            worked_seconds: totalWorkedSeconds,
            late_count: lateCount,
            early_count: earlyCount,
            unassigned_count: 0,
            ambiguous_count: 0,
          },
          period: { date_from: dateFrom, date_to: dateTo, timezone: 'Asia/Ho_Chi_Minh', employee_name: null },
          unassigned_events: [],
          ambiguous_events: [],
          exception_lists_truncated: false,
        });
      }

      // Corrections
      if (url.pathname === '/api/admin/timesheets/corrections/entries') {
        return json({ items: store.data.punches, has_more: false });
      }
      if (url.pathname === '/api/admin/timesheets/corrections/punches' && method === 'POST') {
        const emp = store.data.employees.find(e => e.id === bodyData.employee_id);
        if (!emp) return error('Không tìm thấy nhân viên', 404);
        const newPunch: PunchEntry = {
          id: `punch-${Date.now().toString(36)}`,
          employee_id: emp.id,
          employee_code: emp.code,
          employee_name: emp.name,
          direction: bodyData.direction === 'out' ? 'out' : 'in',
          occurred_at: bodyData.occurred_at || new Date().toISOString(),
          voided: false,
          kind: 'manual',
          reason: bodyData.reason || 'Điều chỉnh thủ công',
          created_at: new Date().toISOString(),
        };
        store.data.punches.unshift(newPunch);
        store.save();
        return json(newPunch);
      }

      const matchVoidPunch = url.pathname.match(/^\/api\/admin\/timesheets\/corrections\/entries\/([^/]+)\/void$/);
      if (matchVoidPunch && method === 'POST') {
        const punch = store.data.punches.find(p => p.id === matchVoidPunch[1]);
        if (punch) {
          punch.voided = true;
          punch.revoke_reason = bodyData?.reason || 'Hủy bản ghi';
          punch.revoked_at = new Date().toISOString();
          store.save();
        }
        return json({ success: true });
      }

      // Adjustments events (raw punches for adjustments panel)
      if (url.pathname === '/api/admin/timesheets/adjustments/events') {
        const empId = url.searchParams.get('employee_id');
        let filtered = store.data.punches;
        if (empId) filtered = filtered.filter(p => p.employee_id === empId);
        return json({ items: filtered, has_more: false });
      }

      // Adjustments history and creation
      if (url.pathname === '/api/admin/timesheets/adjustments') {
        if (method === 'GET') {
          return json({ items: store.data.adjustments || [], has_more: false });
        }
        if (method === 'POST') {
          const kind = bodyData?.kind || 'add';
          const emp = store.data.employees.find(e => e.id === bodyData?.employee_id) || store.data.employees[0];
          const newAdj: PunchEntry = {
            id: `adj-${Date.now().toString(36)}`,
            employee_id: emp.id,
            employee_code: emp.code,
            employee_name: emp.name,
            direction: bodyData?.direction === 'out' ? 'out' : 'in',
            occurred_at: bodyData?.local_time ? new Date(bodyData.local_time).toISOString() : new Date().toISOString(),
            voided: false,
            kind: kind,
            reason: bodyData?.reason || 'Điều chỉnh thủ công',
            created_at: new Date().toISOString(),
          };
          if (!store.data.adjustments) store.data.adjustments = [];
          store.data.adjustments.unshift(newAdj);

          if (kind === 'add') {
            store.data.punches.unshift(newAdj);
          } else if (kind === 'void') {
            const targetId = bodyData?.target_event_id || bodyData?.target_adjustment_id;
            const target = store.data.punches.find(p => p.id === targetId);
            if (target) {
              target.voided = true;
              target.revoke_reason = bodyData?.reason;
            }
          }
          store.save();
          return json(newAdj);
        }
      }

      const matchRevokeAdj = url.pathname.match(/^\/api\/admin\/timesheets\/adjustments\/([^/]+)\/revoke$/);
      if (matchRevokeAdj && method === 'POST') {
        const id = matchRevokeAdj[1];
        const adjs = store.data.adjustments || [];
        const adj = adjs.find(a => a.id === id);
        if (adj) {
          adj.revoked_at = new Date().toISOString();
          adj.revoke_reason = bodyData?.reason || 'Thu hồi điều chỉnh';
        }
        store.save();
        return json({ success: true });
      }

      // Single month period
      const matchPeriodMonth = url.pathname.match(/^\/api\/admin\/timesheets\/periods\/([^/]+)$/);
      if (matchPeriodMonth && method === 'GET') {
        const m = matchPeriodMonth[1];
        let p = store.data.periods.find(x => x.month === m);
        if (!p) {
          p = { month: m, status: 'open', revision: 1, snapshots: [] };
          store.data.periods.push(p);
          store.save();
        }
        return json(p);
      }

      // Periods
      if (url.pathname === '/api/admin/timesheets/periods') {
        return json({ items: store.data.periods });
      }
      const matchPeriodFinalize = url.pathname.match(/^\/api\/admin\/timesheets\/periods\/([^/]+)\/finalize$/);
      if (matchPeriodFinalize && method === 'POST') {
        const month = matchPeriodFinalize[1];
        let p = store.data.periods.find(x => x.month === month);
        if (!p) {
          p = { month, status: 'closed', revision: 1, snapshots: [] };
          store.data.periods.push(p);
        }
        p.status = 'closed';
        p.revision = (p.revision || 0) + 1;
        p.snapshots.push({
          revision: p.revision,
          created_at: new Date().toISOString(),
          reason: bodyData?.reason || 'Chốt kỳ công tháng',
          summary: { row_count: store.data.employees.length, worked_seconds: 576000 },
        });
        store.save();
        return json(p);
      }

      // Timesheet CSV export
      if (url.pathname === '/api/admin/timesheets/export') {
        const csvContent =
          'Mã NV,Họ và tên,Phòng ban,Ngày,Vào ca,Ra ca,Số giờ làm,Đi muộn\n' +
          store.data.employees
            .map(e => `${e.code},"${e.name}","${e.department}",${new Date().toLocaleDateString('vi-VN')},08:00,17:00,8.0,0`)
            .join('\n');
        return new Response(new Blob([csvContent], { type: 'text/csv;charset=utf-8' }), {
          status: 200,
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="bang-cong-local.csv"',
          },
        });
      }

      // 8. Recognition Calibration & PAD
      if (url.pathname === '/api/admin/recognition/calibration/coverage') {
        const offset = parseInt(url.searchParams.get('offset') || '0', 10);
        const limit = parseInt(url.searchParams.get('limit') || '100', 10);
        const emps = store.data.employees.filter(e => e.active);
        const items = emps.map((e, idx) => ({
          employee_id: e.id,
          employee_code: e.code,
          employee_name: e.name,
          enrollment_samples: e.template_count || 5,
          calibration_samples: idx < 8 ? 3 : 0,
          calibration_collections: idx < 8 ? 1 : 0,
          role: 'enrolled',
          missing_calibration_samples: idx < 8 ? 0 : 3,
        }));
        return json({
          items: items.slice(offset, offset + limit),
          total: items.length,
          offset,
          limit,
          minimum_probe_samples: 3,
          summary: {
            enrolled_people: items.length,
            known_people_missing_probes: 2,
            known_probe_samples_missing: 6,
            outside_probe_people: 1,
            outside_people_missing: 0,
            data_coverage_ready: true,
          },
        });
      }

      if (url.pathname === '/api/admin/recognition/calibration') {
        return json({
          status: 'ready',
          reasons: [],
          coverage: {
            enrolled_people: 10,
            enrollment_samples: 45,
            known_probe_people: 8,
            known_probes: 24,
            unknown_probe_people: 2,
            unknown_probes: 6,
            completed_collections: 10,
          },
          candidate: {
            threshold: 0.36,
            minimum_margin: 0.12,
            correct_samples: 24,
            known_samples: 24,
            single_sample_correct_rate: 1.0,
          },
          same_person_diagnostics: {
            samples: 24,
            minimum: 0.42,
            median: 0.68,
            maximum: 0.89,
            mean: 0.67,
          },
          reference_experiments: [
            {
              reference_cap: 1,
              reference_images_used: 10,
              enrolled_people: 10,
              people_below_reference_cap: 0,
              known_probe_people: 8,
              known_probe_samples: 24,
              known_top1_correct_samples: 22,
              known_expected_person_scores: { minimum: 0.38, median: 0.64, maximum: 0.85 },
            },
            {
              reference_cap: 3,
              reference_images_used: 30,
              enrolled_people: 10,
              people_below_reference_cap: 0,
              known_probe_people: 8,
              known_probe_samples: 24,
              known_top1_correct_samples: 24,
              known_expected_person_scores: { minimum: 0.42, median: 0.68, maximum: 0.89 },
            },
            {
              reference_cap: 5,
              reference_images_used: 45,
              enrolled_people: 10,
              people_below_reference_cap: 1,
              known_probe_people: 8,
              known_probe_samples: 24,
              known_top1_correct_samples: 24,
              known_expected_person_scores: { minimum: 0.45, median: 0.71, maximum: 0.91 },
            },
          ],
        });
      }

      if (url.pathname === '/api/admin/pad/status') {
        return json({ ready: true });
      }
      if (url.pathname === '/api/admin/pad/preview') {
        return json({
          live_score: 0.94,
          is_live: true,
          spoof_type: 'none',
          face_box: [160, 100, 260, 260],
          feedback: 'Khuôn mặt người thật trực tiếp',
        });
      }
      if (url.pathname === '/api/admin/recognition/pending') {
        return json({ items: [] });
      }

      // 9. Operations status
      if (url.pathname === '/api/admin/operations/status') {
        return json({
          checked_at: new Date().toISOString(),
          database_ok: true,
          recognition_ready: true,
          experimental_pad_ready: true,
          attendance_enabled: true,
          attendance_mode: 'functional_trial',
          supervisor: { running: true, state: 'active', restart_count: 0 },
          disk: { free_bytes: 48318382080, total_bytes: 107374182400 },
          backup: {
            available: true,
            kind: 'sqlite_local',
            encrypted: true,
            checksum_verified: true,
            updated_at: new Date(Date.now() - 3600000).toISOString(),
            overdue: false,
          },
          alerts: [],
          recovery_key_preserved: true,
        });
      }

      if (url.pathname === '/api/admin/operations/recovery-key/export') {
        return json({
          key_payload: 'ENC-REC-KEY-LOCAL-CHAMCONG-2026',
          message: 'Đã xuất và xác thực khóa khôi phục an toàn tại máy chủ local.',
        });
      }

      // 10. Kiosk Recognition Live Pipeline
      if (url.pathname === '/api/kiosk/recognition/preview') {
        // Face detection in kiosk view
        return json({
          ready: true,
          face_present: true,
          feedback: 'Nhìn thẳng và giữ yên trong khung hình.',
          face_box: [140, 100, 280, 280],
        });
      }

      if (url.pathname === '/api/kiosk/recognition/sessions') {
        if (method === 'POST') {
          const requestId = bodyData?.request_id || `req-${Date.now().toString(36)}`;
          const activeEmps = store.data.employees.filter(e => e.active);
          const assignedEmp = activeEmps[0] || { code: 'NV001', name: 'Nguyễn Văn An' };

          const session: RecognitionSession = {
            request_id: requestId,
            state: 'pending',
            next_frame_index: 1,
            capture_nonce: `nonce-${Date.now()}`,
            needs_supervisor: false,
            employee_code: assignedEmp.code,
            employee_name: assignedEmp.name,
          };
          store.sessions.set(requestId, session);
          return json(session);
        }
      }

      const matchSessionGet = url.pathname.match(/^\/api\/kiosk\/recognition\/sessions\/([^/]+)$/);
      if (matchSessionGet && method === 'GET') {
        const id = matchSessionGet[1];
        const s = store.sessions.get(id);
        if (!s) return error('Phiên không tồn tại', 404);
        return json(s);
      }

      const matchSessionFrame = url.pathname.match(/^\/api\/kiosk\/recognition\/sessions\/([^/]+)\/frames\/(\d+)$/);
      if (matchSessionFrame && method === 'POST') {
        const id = matchSessionFrame[1];
        const frameIdx = parseInt(matchSessionFrame[2], 10);
        const s = store.sessions.get(id);
        if (!s) return error('Phiên không tồn tại', 404);

        if (frameIdx === 1) {
          s.next_frame_index = 2;
          s.capture_nonce = `nonce-2-${Date.now()}`;
          return json({
            state: 'pending',
            next_frame_index: 2,
            capture_nonce: s.capture_nonce,
            stable_frames: 1,
            feedback: 'Đang chụp nhận diện (1/3)… Giữ yên.',
            face_box: [140, 100, 280, 280],
          });
        }
        if (frameIdx === 2) {
          s.next_frame_index = 3;
          s.capture_nonce = `nonce-3-${Date.now()}`;
          return json({
            state: 'pending',
            next_frame_index: 3,
            capture_nonce: s.capture_nonce,
            stable_frames: 2,
            feedback: 'Đang so khớp khuôn mặt (2/3)…',
            face_box: [140, 100, 280, 280],
          });
        }
        // Frame 3: Verified!
        s.state = 'verified';
        s.needs_supervisor = false;
        return json({
          state: 'verified',
          needs_supervisor: false,
          stable_frames: 3,
          feedback: `Nhận diện chính xác: ${s.employee_code} · ${s.employee_name}!`,
          face_box: [140, 100, 280, 280],
        });
      }

      // Kiosk Attendance Commit
      const matchCommit = url.pathname.match(/^\/api\/kiosk\/attendance\/([^/]+)\/commit$/);
      if (matchCommit && method === 'POST') {
        const id = matchCommit[1];
        const s = store.sessions.get(id);
        const empCode = s?.employee_code || 'NV001';
        const empName = s?.employee_name || 'Nguyễn Văn An';
        const emp = store.data.employees.find(e => e.code === empCode) || store.data.employees[0];
        const currentDev = store.data.devices.find(d => d.id === store.data.currentDeviceId) || store.data.devices[0];
        const dir = currentDev?.direction || 'in';

        const receipt = {
          status: 'recorded',
          request_id: id,
          event_id: `evt-${Date.now().toString(36)}`,
          employee_code: empCode,
          employee_name: empName,
          server_time: new Date().toISOString(),
          direction: dir,
        };

        if (s) {
          s.state = 'used';
          s.receipt = receipt;
        }

        // Add to punches log
        store.data.punches.unshift({
          id: receipt.event_id,
          employee_id: emp?.id || 'emp-01',
          employee_code: empCode,
          employee_name: empName,
          direction: dir,
          occurred_at: receipt.server_time,
          voided: false,
          kind: 'kiosk',
          created_at: receipt.server_time,
        });
        store.save();

        return json(receipt);
      }

      // Default fallback for any unhandled /api route
      console.warn('Unhandled mock API route:', method, url.pathname);
      return json({ ok: true });
    } catch (err) {
      console.error('Mock API error:', err);
      return error('Lỗi xử lý yêu cầu mock API', 500);
    }
  };

  try {
    Object.defineProperty(window, 'fetch', {
      value: customFetch,
      configurable: true,
      writable: true,
    });
  } catch {
    try {
      Object.defineProperty(Object.getPrototypeOf(window), 'fetch', {
        value: customFetch,
        configurable: true,
        writable: true,
      });
    } catch {
      try {
        (window as any).fetch = customFetch;
      } catch (err) {
        console.warn('Could not intercept window.fetch directly:', err);
      }
    }
  }
}
