import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
const ALLOWED_ORIGINS = new Set([
  "https://hadikhameesy.github.io",
  "http://localhost:5500",
  "http://127.0.0.1:5500",
]);
const PIPELINES = [
  "animated-explainer", "animation", "avatar-spokesperson", "character-animation",
  "cinematic", "clip-factory", "documentary-montage", "framework-smoke", "hybrid",
  "localization-dub", "podcast-repurpose", "screen-demo", "talking-head",
];

function cors(origin: string | null): HeadersInit {
  const allowed = origin && ALLOWED_ORIGINS.has(origin) ? origin : "https://hadikhameesy.github.io";
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, last-event-id",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}
function json(data: unknown, status = 200, origin: string | null = null): Response {
  return new Response(JSON.stringify(data), {
    status, headers: { ...cors(origin), "Content-Type": "application/json; charset=utf-8" },
  });
}
function fail(message: string, status: number, origin: string | null): Response {
  return json({ error: { code: "request_error", message } }, status, origin);
}
function validAspect(value: unknown): value is string {
  return ["16:9", "9:16", "1:1", "4:5"].includes(String(value));
}

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  const url = new URL(req.url);
  const routeAt = url.pathname.indexOf("/api/v1");
  const path = routeAt >= 0 ? url.pathname.slice(routeAt) : url.pathname;
  if (req.method === "GET" && (path === "/health" || path.endsWith("/health"))) {
    return json({ status: "ok", service: "openmontage-supabase-edge-api" }, 200, origin);
  }
  if (!["GET", "POST"].includes(req.method)) return fail("Method not allowed", 405, origin);

  const auth = req.headers.get("authorization") || "";
  const token = auth.match(/^Bearer\s+(.+)$/i)?.[1];
  if (!token) return fail("Authentication required", 401, origin);

  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: `Bearer ${token}` } },
  });
  const { data: authData, error: authError } = await supabase.auth.getUser(token);
  if (authError || !authData.user) return fail("Invalid or expired access token", 401, origin);

  try {
    if (req.method === "GET" && path === "/api/v1/version") {
      return json({ application: "OpenMontage", version: "0.4.0", api: "v1" }, 200, origin);
    }
    if (req.method === "GET" && path === "/api/v1/pipelines") {
      return json({ items: PIPELINES.map((id) => ({
        id, name: id.replaceAll("-", " ").replace(/\b\w/g, (m) => m.toUpperCase()),
        version: "manifest", category: "video", available: true, stages: [],
      })) }, 200, origin);
    }
    if (req.method === "GET" && path === "/api/v1/projects") {
      const { data, error } = await supabase.from("projects")
        .select("id,name,brief,pipeline_id,aspect_ratio,created_at,updated_at")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return json({ items: data || [] }, 200, origin);
    }
    if (req.method === "POST" && path === "/api/v1/projects") {
      const body = await req.json();
      const name = String(body.name || "").trim();
      const brief = String(body.brief || "").trim();
      const pipeline_id = String(body.pipeline_id || "");
      const aspect_ratio = body.aspect_ratio || "16:9";
      if (name.length < 1 || name.length > 120 || brief.length < 1 || brief.length > 12000 ||
          !PIPELINES.includes(pipeline_id) || !validAspect(aspect_ratio)) {
        return fail("Invalid project fields", 422, origin);
      }
      const { data, error } = await supabase.from("projects").insert({
        owner_id: authData.user.id, name, brief, pipeline_id, aspect_ratio,
      }).select("*").single();
      if (error) throw error;
      return json(data, 201, origin);
    }
    if (req.method === "GET" && path === "/api/v1/jobs") {
      const { data, error } = await supabase.from("jobs")
        .select("id,project_id,pipeline_id,status,progress,stage,error_code,created_at,started_at,finished_at")
        .order("created_at", { ascending: false }).limit(100);
      if (error) throw error;
      return json({ items: data || [] }, 200, origin);
    }

    const projectJobs = path.match(/^\/api\/v1\/projects\/([0-9a-f-]+)\/jobs$/i);
    if (projectJobs && req.method === "GET") {
      const { data, error } = await supabase.from("jobs").select("*")
        .eq("project_id", projectJobs[1]).order("created_at", { ascending: false });
      if (error) throw error;
      return json({ items: data || [] }, 200, origin);
    }
    if (projectJobs && req.method === "POST") {
      const { data: project, error: projectError } = await supabase.from("projects")
        .select("id,pipeline_id").eq("id", projectJobs[1]).maybeSingle();
      if (projectError) throw projectError;
      if (!project) return fail("Project not found", 404, origin);
      const body = await req.json().catch(() => ({}));
      const options = body.options && typeof body.options === "object" && !Array.isArray(body.options) ? body.options : {};
      const { data, error } = await supabase.from("jobs").insert({
        owner_id: authData.user.id, project_id: project.id,
        pipeline_id: project.pipeline_id, status: "queued", payload: options,
      }).select("*").single();
      if (error) throw error;
      return json(data, 202, origin);
    }

    const jobEvents = path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/events$/i);
    if (jobEvents && req.method === "GET") {
      const after = Math.max(0, Number(url.searchParams.get("after") || 0));
      const { data, error } = await supabase.from("job_events")
        .select("sequence,event_type,stage,progress,message,data,created_at")
        .eq("job_id", jobEvents[1]).gt("sequence", after)
        .order("sequence", { ascending: true }).limit(500);
      if (error) throw error;
      return json({ items: data || [] }, 200, origin);
    }

    const cancel = path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/cancel$/i);
    if (cancel && req.method === "POST") {
      const { data, error } = await supabase.rpc("request_openmontage_job_cancel", {
        p_job_id: cancel[1],
      });
      if (error) throw error;
      if (!data?.length) return fail("Job is not cancellable or is not accessible", 409, origin);
      return json(data[0], 200, origin);
    }

    const job = path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)$/i);
    if (job && req.method === "GET") {
      const { data, error } = await supabase.from("jobs").select("*")
        .eq("id", job[1]).maybeSingle();
      if (error) throw error;
      if (!data) return fail("Job not found", 404, origin);
      return json(data, 200, origin);
    }
    return fail("Route not found", 404, origin);
  } catch (error) {
    console.error("OpenMontage edge API request failed", error instanceof Error ? error.message : "unknown");
    return fail("Request could not be completed", 500, origin);
  }
});
