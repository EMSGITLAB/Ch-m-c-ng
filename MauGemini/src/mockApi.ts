// Mock API Interceptor for AI Studio Preview Environment (*.run.app)
// Local Windows/VM deployments connect directly to the FastAPI backend.

const todayISO = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });

const MOCK_VENDORS = [
  { id: 'v1', code: 'VINALOG', name: 'Công ty Tiếp vận VinaLog', active: true },
  { id: 'v2', code: 'ANPHA-SEC', name: 'Dịch vụ Kỹ thuật & Bảo vệ Anpha', active: true },
];

const MOCK_BATCHES = [
  {
    id: 'b1',
    partner_id: 'v1',
    name: 'Ca Sáng Kho Lạnh A',
    site: 'Kho Lạnh A - Cổng 2',
    work_date: todayISO,
    state: 'open',
    capacity: 30,
    requested_count: 25,
    starts_at: `${todayISO}T01:00:00Z`,
    ends_at: `${todayISO}T10:00:00Z`,
    timezone: 'Asia/Ho_Chi_Minh',
    retention_hours: 48,
    threshold: 0.48,
  },
  {
    id: 'b2',
    partner_id: 'v2',
    name: 'Tổ Bảo Trì Điện Công Nghiệp',
    site: 'Xưởng Cơ Điện B',
    work_date: todayISO,
    state: 'review',
    capacity: 15,
    requested_count: 12,
    starts_at: `${todayISO}T00:30:00Z`,
    ends_at: `${todayISO}T09:30:00Z`,
    timezone: 'Asia/Ho_Chi_Minh',
    retention_hours: 48,
    threshold: 0.48,
  },
];

const MOCK_DEVICES = [
  {
    id: 'dev-1',
    name: 'iPad Sảnh Chính 01',
    direction: 'in' as 'in' | 'out',
    active: true,
    paired: true,
    workflow: 'employee' as 'employee' | 'partner',
    partner_batch_id: null as string | null,
    last_seen_at: new Date().toISOString(),
  },
  {
    id: 'dev-2',
    name: 'Tablet Cổng Kho Đối Tác',
    direction: 'in' as 'in' | 'out',
    active: true,
    paired: true,
    workflow: 'partner' as 'employee' | 'partner',
    partner_batch_id: 'b1' as string | null,
    last_seen_at: new Date().toISOString(),
  },
];

const MOCK_BINDINGS = [{ device_id: 'dev-2', batch_id: 'b1', active: true }];

const MOCK_PARTNER_WORKERS = [
  {
    id: 'pw-1',
    code: 'D30-VINALOG-0001',
    name: 'Phạm Văn Hùng',
    name_source: 'voice',
    state: 'active',
    name_revision: 1,
    name_confirmed: true,
    admission_approved: true,
    pending_expires_at: new Date(Date.now() + 1000 * 60 * 15).toISOString(),
    in_at: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
    out_at: null as string | null,
  },
  {
    id: 'pw-2',
    code: 'D30-VINALOG-0002',
    name: 'Đỗ Thành Nam',
    name_source: 'manual',
    state: 'completed',
    name_revision: 1,
    name_confirmed: true,
    admission_approved: true,
    pending_expires_at: new Date(Date.now() + 1000 * 60 * 15).toISOString(),
    in_at: new Date(Date.now() - 1000 * 60 * 300).toISOString(),
    out_at: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
  },
];

const MOCK_EMPLOYEES = [
  {
    id: 1,
    code: 'NV001',
    name: 'Nguyễn Văn An',
    department: 'Kỹ thuật',
    active: true,
    template_count: 5,
    collection_count: 1,
    imported_photo_count: 0,
    profile_photo_url: null,
    deleted_at: null,
  },
  {
    id: 2,
    code: 'NV002',
    name: 'Trần Thị Bình',
    department: 'Nhân sự',
    active: true,
    template_count: 4,
    collection_count: 1,
    imported_photo_count: 0,
    profile_photo_url: null,
    deleted_at: null,
  },
];

export function initMockApi() {
  const originalFetch = window.fetch.bind(window);

  const customFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;

    if (!urlStr.includes('/api/')) {
      return originalFetch(input, init);
    }

    const url = new URL(urlStr, window.location.origin);
    const path = url.pathname;
    const method = (init?.method || 'GET').toUpperCase();

    await new Promise(r => setTimeout(r, 90));

    const jsonResponse = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });

    // --- SYSTEM & KIOSK STATUS ---
    if (path === '/api/system/status' || path === '/api/kiosk/status') {
      return jsonResponse({
        server_time: new Date().toISOString(),
        timezone: 'Asia/Ho_Chi_Minh',
        recognition_ready: true,
        attendance_enabled: true,
        attendance_mode: 'production',
        pilot_people: MOCK_EMPLOYEES.length,
        pilot_scope: 'all',
        capture_max_edge: 1280,
        message: 'Hệ thống nhận diện sẵn sàng.',
        version: '0.2.0',
      });
    }

    if (path === '/api/kiosk/device') {
      const isPartnerHash = window.location.hash.startsWith('#partner');
      const dev = isPartnerHash ? MOCK_DEVICES[1] : MOCK_DEVICES[0];
      if (method === 'PATCH' && init?.body) {
        const body = JSON.parse(init.body as string);
        if (body.direction) dev.direction = body.direction;
      }
      return jsonResponse(dev);
    }

    if (path === '/api/kiosk/pair' && method === 'POST') {
      return jsonResponse(MOCK_DEVICES[0]);
    }

    // --- PARTNER KIOSK ENDPOINTS ---
    if (path === '/api/kiosk/partners/context') {
      const activeBatch = MOCK_BATCHES[0];
      const vendor = MOCK_VENDORS.find(v => v.id === activeBatch.partner_id) || MOCK_VENDORS[0];
      return jsonResponse({
        partner: { name: vendor.name, code: vendor.code },
        batch: {
          id: activeBatch.id,
          name: activeBatch.name,
          site: activeBatch.site,
          state: activeBatch.state,
          starts_at: activeBatch.starts_at,
          ends_at: activeBatch.ends_at,
          timezone: activeBatch.timezone,
          rules: { functional_trial: false },
        },
        direction: MOCK_DEVICES[1].direction,
        recognition_ready: true,
        recording_enabled: true,
        message: 'Sẵn sàng tiếp nhận đối tác.',
      });
    }

    if (path === '/api/kiosk/partners/preview' && method === 'POST') {
      return jsonResponse({
        ready: false,
        face_present: true,
        feedback: 'Giữ yên khuôn mặt trong khung ngắm để xác thực tự động.',
        face_box: [0.28, 0.18, 0.72, 0.82],
      });
    }

    // --- ADMIN SESSION ---
    if (path === '/api/admin/session' || path === '/api/admin/me') {
      return jsonResponse({
        authenticated: true,
        username: 'admin',
        csrf_token: 'csrf-preview-token',
      });
    }

    if (path === '/api/admin/login' && method === 'POST') {
      return jsonResponse({
        authenticated: true,
        username: 'admin',
        csrf_token: 'csrf-preview-token',
      });
    }

    // --- ADMIN PARTNERS ---
    if (path === '/api/admin/partners') {
      if (method === 'GET') return jsonResponse({ items: MOCK_VENDORS });
      if (method === 'POST' && init?.body) {
        const body = JSON.parse(init.body as string);
        const created = {
          id: 'v' + (MOCK_VENDORS.length + 1),
          code: body.code || 'PARTNER',
          name: body.name || 'Đối tác mới',
          active: true,
        };
        MOCK_VENDORS.push(created);
        return jsonResponse(created, 201);
      }
    }

    if (path === '/api/admin/partners/batches/list') {
      return jsonResponse({ items: MOCK_BATCHES, has_more: false });
    }

    if (path === '/api/admin/partners/batches' && method === 'POST') {
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const created = {
        id: 'b' + (MOCK_BATCHES.length + 1),
        partner_id: body.partner_id || 'v1',
        name: body.name || 'Ca tăng cường',
        site: body.site || 'Sàn A',
        work_date: body.work_date || todayISO,
        state: 'draft',
        capacity: Number(body.capacity || 30),
        requested_count: Number(body.requested_count || 30),
        starts_at: `${body.work_date || todayISO}T01:00:00Z`,
        ends_at: `${body.work_date || todayISO}T10:00:00Z`,
        timezone: 'Asia/Ho_Chi_Minh',
        retention_hours: 48,
        threshold: 0.48,
      };
      MOCK_BATCHES.unshift(created);
      return jsonResponse(created, 201);
    }

    if (path.startsWith('/api/admin/partners/batches/') && path.endsWith('/state') && method === 'POST') {
      const id = path.split('/')[5];
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const batch = MOCK_BATCHES.find(b => b.id === id);
      if (batch && body.state) batch.state = body.state;
      return jsonResponse(batch || MOCK_BATCHES[0]);
    }

    if (path.startsWith('/api/admin/partners/batches/') && path.endsWith('/capacity') && method === 'POST') {
      const id = path.split('/')[5];
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const batch = MOCK_BATCHES.find(b => b.id === id);
      if (batch && body.capacity) batch.capacity = Number(body.capacity);
      return jsonResponse(batch || MOCK_BATCHES[0]);
    }

    if (path.startsWith('/api/admin/partners/batches/') && path.endsWith('/workers')) {
      return jsonResponse({ items: MOCK_PARTNER_WORKERS, has_more: false });
    }

    if (path.startsWith('/api/admin/partners/batches/') && path.endsWith('/report')) {
      const id = path.split('/')[5];
      const batch = MOCK_BATCHES.find(b => b.id === id) || MOCK_BATCHES[0];
      const vendor = MOCK_VENDORS.find(v => v.id === batch.partner_id) || MOCK_VENDORS[0];
      return jsonResponse({
        source_hash: 'hash-preview-001',
        as_of: new Date().toISOString(),
        closed: batch.state === 'closed',
        partner: vendor,
        batch,
        summary: {
          requested: 25,
          capacity: batch.capacity,
          admitted: 2,
          complete: 1,
          incomplete: 1,
          pending: 0,
          available_slots: batch.capacity - 2,
          total_worked_seconds: 28800,
        },
        note: 'Bảng công đối soát tự động từ dữ liệu nhận diện tại quầy đối tác.',
        rows: [
          {
            worker_id: 'pw-2',
            code: 'D30-VINALOG-0002',
            name: 'Đỗ Thành Nam',
            admitted: true,
            status: 'complete',
            status_label: 'Đủ Vào/Ra',
            in_at: MOCK_PARTNER_WORKERS[1].in_at,
            out_at: MOCK_PARTNER_WORKERS[1].out_at,
            raw_in_at: MOCK_PARTNER_WORKERS[1].in_at,
            raw_out_at: MOCK_PARTNER_WORKERS[1].out_at,
            worked_seconds: 16800,
            elapsed_seconds: 16800,
            unpaid_break_seconds: 0,
            outside_shift_seconds: 0,
            adjustment_revision: 0,
            adjustments: [],
            original_events: [
              { id: 'ev-1', direction: 'in', server_time: MOCK_PARTNER_WORKERS[1].in_at! },
              { id: 'ev-2', direction: 'out', server_time: MOCK_PARTNER_WORKERS[1].out_at! },
            ],
          },
          {
            worker_id: 'pw-1',
            code: 'D30-VINALOG-0001',
            name: 'Phạm Văn Hùng',
            admitted: true,
            status: 'missing_out',
            status_label: 'Chưa ghi lượt Ra',
            in_at: MOCK_PARTNER_WORKERS[0].in_at,
            out_at: null,
            raw_in_at: MOCK_PARTNER_WORKERS[0].in_at,
            raw_out_at: null,
            worked_seconds: 12000,
            elapsed_seconds: 12000,
            unpaid_break_seconds: 0,
            outside_shift_seconds: 0,
            adjustment_revision: 0,
            adjustments: [],
            original_events: [{ id: 'ev-3', direction: 'in', server_time: MOCK_PARTNER_WORKERS[0].in_at! }],
          },
        ],
      });
    }

    if (path === '/api/admin/partners/devices/list') {
      return jsonResponse({ items: MOCK_BINDINGS });
    }

    if (path.startsWith('/api/admin/partners/devices/') && method === 'PUT') {
      const deviceId = path.split('/')[5];
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const existing = MOCK_BINDINGS.find(b => b.device_id === deviceId);
      if (existing) {
        existing.batch_id = body.batch_id;
        existing.active = true;
      } else {
        MOCK_BINDINGS.push({ device_id: deviceId, batch_id: body.batch_id, active: true });
      }
      return jsonResponse({ ok: true });
    }

    if (path.startsWith('/api/admin/partners/devices/') && path.endsWith('/unbind') && method === 'POST') {
      const deviceId = path.split('/')[5];
      const existing = MOCK_BINDINGS.find(b => b.device_id === deviceId);
      if (existing) existing.active = false;
      return jsonResponse({ ok: true });
    }

    // --- ADMIN EMPLOYEES & DEVICES ---
    if (path === '/api/admin/employees') {
      return jsonResponse({
        items: MOCK_EMPLOYEES,
        total: MOCK_EMPLOYEES.length,
        departments: ['Kỹ thuật', 'Nhân sự', 'Vận hành'],
      });
    }

    if (path === '/api/admin/devices') {
      return jsonResponse({ items: MOCK_DEVICES });
    }

    if (path === '/api/admin/calibration/coverage' || path === '/api/admin/coverage') {
      return jsonResponse({
        summary: {
          active_people: MOCK_EMPLOYEES.length,
          enrolled_people: MOCK_EMPLOYEES.length,
          ready_people: MOCK_EMPLOYEES.length,
          missing_enrollment_people: 0,
          partial_pose_people: 0,
          onboarding_people: 0,
          min_ready_templates: 3,
          max_templates_per_person: 5,
        },
        items: [],
      });
    }

    return jsonResponse({ items: [], total: 0, ok: true });
  };

  try {
    Object.defineProperty(window, 'fetch', {
      value: customFetch,
      writable: true,
      configurable: true,
    });
  } catch {
    // ignore if read-only
  }
}
