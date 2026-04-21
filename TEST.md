# GhostFabric — Environment & API Testing Guide

## 1. Configure `.env`

Copy the example file and fill in each key:

```bash
cp .env.example .env
```

### Key-by-Key Reference

| Key | Where to get it | Example value |
|-----|----------------|---------------|
| `AWS_ACCESS_KEY_ID` | AWS Console → IAM → Your user → Security credentials → Access keys | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | Shown once when creating the access key above | `wJalrXUtn...` |
| `AWS_REGION` | Region where your S3 bucket lives (e.g. `ap-south-1` for Mumbai) | `us-east-1` |
| `S3_BUCKET_NAME` | AWS Console → S3 → bucket name you created | `ghostfabric-outputs` |
| `NODE_PORT` | Port Node.js server listens on — change only if 3000 is taken | `3000` |
| `NODE_ENV` | `development` locally, `production` on server | `development` |
| `PYTHON_SERVICE_URL` | URL of the FastAPI service — keep default unless Docker changes it | `http://localhost:8000` |
| `JOB_CONCURRENCY` | Max simultaneous ML jobs — set `1` unless you have multiple GPUs | `1` |
| `CIRCUIT_BREAKER_TIMEOUT` | ms before a job is considered hung | `120000` |
| `CIRCUIT_BREAKER_ERROR_THRESHOLD` | % failures that trip the breaker | `50` |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | ms before breaker tries again after tripping | `30000` |
| `SHARED_TMP_DIR` | Shared RAM disk path between Node and Python | `/dev/shm/ghostfabric` |
| `LOG_LEVEL` | `debug` for local dev, `info` for staging/prod | `debug` |

> **AWS minimal IAM policy** — the IAM user only needs `s3:PutObject` and `s3:GetObject`
> on `arn:aws:s3:::ghostfabric-outputs/*`.

---

## 2. Services & Base URLs

| Service | Default URL | Started by |
|---------|-------------|-----------|
| Node.js gateway | `http://localhost:3000` | `npm start` / pm2 |
| Python FastAPI | `http://localhost:8000` | `uvicorn app.main:app` |
| FastAPI Swagger UI | `http://localhost:8000/docs` | auto |

---

## 3. API Endpoints

### Node.js Gateway (port 3000)

#### `GET /health`
Returns queue size — use to confirm Node is running.

**Response 200**
```json
{ "status": "ok", "queue_size": 0 }
```

---

#### `POST /jobs`
Submit a garment image for ghost-mannequin processing.

- **Content-Type:** `multipart/form-data`
- **Field:** `image` — JPEG or PNG, max 50 MB

**Response 202** — job accepted, processing starts async
```json
{ "job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued" }
```

**Error cases**

| Status | Reason |
|--------|--------|
| 400 | No image field in request |
| 415 | File is not JPEG or PNG |
| 500 | Internal server error |

---

#### WebSocket `ws://localhost:3000`
Connect after submitting a job to receive live progress events.

**Event shape**
```json
{
  "job_id": "550e8400-...",
  "status": "processing:segmentation",
  "progress": 10,
  "result_url": null
}
```

**Status progression**
```
queued → processing:segmentation → uploading → completed
                                             ↘ failed:internal
```

When `status` is `completed`, `result_url` contains the S3 URL of the `.glb` file.

---

### Python FastAPI (port 8000)

#### `GET /health`
Checks GPU availability and free VRAM.

**Response 200**
```json
{ "status": "ok", "gpu_available": true, "vram_free_gb": 9.42 }
```

---

#### `POST /process`
Direct ML pipeline call (bypasses Node queue — use for debugging the Python service only).

- **Content-Type:** `multipart/form-data`
- **Field:** `image` — JPEG or PNG, max 50 MB

**Response 200**
```json
{ "job_id": "...", "status": "completed", "glb_path": "/dev/shm/ghostfabric/.../output.glb" }
```

---

## 4. Testing in VSCode — REST Client

Install the **REST Client** extension (`humao.rest-client`) in VSCode.

Create a file `ghostfabric/requests.http` with the content below, then click
**Send Request** above any `###` block.

```http
@node = http://localhost:3000
@python = http://localhost:8000

### Node health
GET {{node}}/health

###

### Python health
GET {{python}}/health

###

### Submit a job (Node)
# Replace the file path with an actual JPEG/PNG on your machine
POST {{node}}/jobs
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="image"; filename="garment.jpg"
Content-Type: image/jpeg

< C:/path/to/your/garment.jpg
------Boundary--

###

### Direct Python process (debug only)
POST {{python}}/process
Content-Type: multipart/form-data; boundary=----Boundary

------Boundary
Content-Disposition: form-data; name="image"; filename="garment.jpg"
Content-Type: image/jpeg

< C:/path/to/your/garment.jpg
------Boundary--
```

> **Tip:** REST Client stores the last response — you can copy the `job_id`
> from the `/jobs` response and paste it into a WebSocket client to watch progress.

---

## 5. Testing in Postman

### Import environment

1. Open Postman → Environments → **New**
2. Add two variables:

   | Variable | Initial value |
   |----------|--------------|
   | `node_url` | `http://localhost:3000` |
   | `python_url` | `http://localhost:8000` |

3. Save as **GhostFabric Local** and select it.

---

### Request collection

#### Node — Health check
- **Method:** GET
- **URL:** `{{node_url}}/health`
- Expected: `200 { "status": "ok" }`

---

#### Node — Submit job
- **Method:** POST
- **URL:** `{{node_url}}/jobs`
- **Body tab:** `form-data`
  - Key: `image` | Type: **File** | Value: select a JPEG/PNG from disk
- Expected: `202 { "job_id": "...", "status": "queued" }`
- **Save `job_id` from the response** — you'll need it for WebSocket tracking.

**Test script (Postman Tests tab)**
```javascript
const body = pm.response.json();
pm.test("Status 202", () => pm.response.to.have.status(202));
pm.test("Has job_id", () => pm.expect(body.job_id).to.be.a("string"));
pm.environment.set("job_id", body.job_id);
```

---

#### Python — Health check
- **Method:** GET
- **URL:** `{{python_url}}/health`
- Expected: `200 { "status": "ok", "gpu_available": true/false, ... }`

---

#### Python — Direct process (debug)
- **Method:** POST
- **URL:** `{{python_url}}/process`
- **Body tab:** `form-data`
  - Key: `image` | Type: **File** | Value: select a JPEG/PNG

---

### WebSocket in Postman

1. **New → WebSocket Request**
2. URL: `ws://localhost:3000`
3. Click **Connect**
4. After submitting a job via HTTP, watch the Messages pane for JSON events
5. Filter by `job_id` using the search bar to isolate your job's events

---

## 6. Quick Smoke-Test Sequence

Run these in order to verify the full stack:

```
1. GET  /health (Node)      → { "status": "ok" }
2. GET  /health (Python)    → { "status": "ok", "gpu_available": true }
3. POST /jobs  (Node)       → 202 + job_id
4. WS   ws://localhost:3000 → events: queued → segmentation → uploading → completed
5. Check S3 bucket          → .glb file present at the result_url
```

If step 2 returns `"gpu_available": false`, the pipeline will still run on CPU — but
expect processing times of several minutes instead of seconds.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Node `/health` times out | Server not running | `npm start` or check pm2 logs |
| Python `/health` times out | FastAPI not started | `uvicorn app.main:app --reload` |
| Job stuck at `queued` | Python service unreachable | Check `PYTHON_SERVICE_URL` in `.env` |
| `failed:internal` on WS | ML pipeline error | Check Python logs: `tail -f python/logs/app.log` |
| S3 upload fails | Wrong AWS credentials | Verify keys with `aws s3 ls s3://<bucket>` |
| `413` on upload | Image > 50 MB | Resize or compress the image |
| `415` on upload | Wrong file type | Only JPEG and PNG are accepted |
