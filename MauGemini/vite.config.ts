import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

function mockApiPlugin(): Plugin {
  return {
    name: 'mock-api-plugin',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/api/') && req.url !== '/health') {
          return next();
        }

        const url = new URL(req.url, 'http://127.0.0.1:3000');
        const sendJson = (data: unknown, status = 200) => {
          res.statusCode = status;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(data));
        };

        if (url.pathname === '/api/system/status' || url.pathname === '/health') {
          return sendJson({
            server_time: new Date().toISOString(),
            timezone: 'Asia/Ho_Chi_Minh',
            recognition_ready: true,
            attendance_enabled: true,
            attendance_mode: 'functional_trial',
            pilot_people: 10,
            pilot_scope: 'all',
            capture_max_edge: 1280,
            message: 'Máy chủ local hoạt động bình thường · Sẵn sàng ghi công',
            version: '0.2.0',
          });
        }

        if (url.pathname === '/api/auth/session' || url.pathname === '/api/auth/login') {
          return sendJson({ username: 'admin', csrf_token: 'mock-csrf-token-12345' });
        }
        if (url.pathname === '/api/auth/setup') {
          return sendJson({ requires_setup: false, local_setup_allowed: true });
        }
        if (url.pathname === '/api/auth/logout') {
          return sendJson({ success: true });
        }
        if (url.pathname === '/api/kiosk/device') {
          return sendJson({
            id: 'dev-01',
            name: 'Camera Cửa Chính (Vào)',
            direction: 'in',
            active: true,
            paired: true,
            last_seen_at: new Date().toISOString(),
          });
        }
        if (url.pathname === '/api/admin/recognition/calibration/coverage') {
          return sendJson({
            items: [
              { employee_id: 'emp-01', employee_code: 'NV001', employee_name: 'Nguyễn Văn An', enrollment_samples: 5, calibration_samples: 3, calibration_collections: 1, role: 'enrolled', missing_calibration_samples: 0 },
              { employee_id: 'emp-02', employee_code: 'NV002', employee_name: 'Trần Thị Bích', enrollment_samples: 5, calibration_samples: 3, calibration_collections: 1, role: 'enrolled', missing_calibration_samples: 0 },
              { employee_id: 'emp-03', employee_code: 'NV003', employee_name: 'Lê Hoàng Cường', enrollment_samples: 4, calibration_samples: 3, calibration_collections: 1, role: 'enrolled', missing_calibration_samples: 0 }
            ],
            total: 3,
            offset: 0,
            limit: 100,
            minimum_probe_samples: 3,
            summary: {
              enrolled_people: 10,
              known_people_missing_probes: 2,
              known_probe_samples_missing: 6,
              outside_probe_people: 1,
              outside_people_missing: 0,
              data_coverage_ready: true,
            },
          });
        }
        if (url.pathname === '/api/admin/timesheets/adjustments/events') {
          return sendJson({ items: [], has_more: false });
        }
        if (url.pathname === '/api/admin/timesheets/adjustments') {
          return sendJson({ items: [], has_more: false });
        }
        const matchPeriodMonth = url.pathname.match(/^\/api\/admin\/timesheets\/periods\/([^/]+)$/);
        if (matchPeriodMonth) {
          return sendJson({ month: matchPeriodMonth[1], status: 'open', revision: 1, snapshots: [] });
        }

        return next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), mockApiPlugin()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
  },
});
