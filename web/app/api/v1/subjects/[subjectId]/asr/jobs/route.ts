import { forwardBackendUpload } from "@/lib/streaming-upload-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The collection path is excluded from the Next proxy matcher because its POST
// must stream the multipart body without Next cloning/capping it.  The same
// exclusion affects GET /asr/jobs, so both methods need a dedicated App Router
// handler.  Forwarding headers (including cookies) lets FastAPI's require_auth
// remain the authority; this route does not create an unauthenticated path.
export function POST(request: Request): Promise<Response> {
  return forwardBackendUpload(request);
}

export function GET(request: Request): Promise<Response> {
  return forwardBackendUpload(request);
}
