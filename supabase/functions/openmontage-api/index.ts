import { createClient } from "npm:@supabase/supabase-js@2";
import { formatSseEvent, parseLastEventId } from "./sse.ts";
const SUPABASE_URL=Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY=Deno.env.get("SUPABASE_ANON_KEY")!;
const ALLOWED_ORIGINS=new Set(["https://hadikhameesy.github.io","http://localhost:5500","http://127.0.0.1:5500"]);
const PIPELINES=["animated-explainer","animation","avatar-spokesperson","character-animation","cinematic","clip-factory","documentary-montage","framework-smoke","hybrid","localization-dub","podcast-repurpose","screen-demo","talking-head"];
const BUCKET="openmontage-private";
function cors(o:string|null):HeadersInit{return{"Access-Control-Allow-Origin":o&&ALLOWED_ORIGINS.has(o)?o:"https://hadikhameesy.github.io","Access-Control-Allow-Headers":"authorization, apikey, content-type, last-event-id","Access-Control-Allow-Methods":"GET, POST, OPTIONS","Access-Control-Max-Age":"86400","Vary":"Origin"};}
function json(d:unknown,s=200,o:string|null=null):Response{return new Response(JSON.stringify(d),{status:s,headers:{...cors(o),"Content-Type":"application/json; charset=utf-8"}});}
function fail(m:string,s:number,o:string|null):Response{return json({error:{code:"request_error",message:m}},s,o);}
function validAspect(v:unknown):boolean{return["16:9","9:16","1:1","4:5"].includes(String(v));}
Deno.serve(async(req:Request)=>{
 const origin=req.headers.get("origin");if(req.method==="OPTIONS")return new Response("ok",{headers:cors(origin)});
 const url=new URL(req.url),at=url.pathname.indexOf("/api/v1"),path=at>=0?url.pathname.slice(at):url.pathname;
 if(req.method==="GET"&&(path==="/health"||path.endsWith("/health")))return json({status:"ok",service:"openmontage-supabase-edge-api"},200,origin);
 if(!["GET","POST"].includes(req.method))return fail("Method not allowed",405,origin);
 if(req.method==="GET"&&path==="/api/v1/version")return json({application:"OpenMontage",version:"0.5.0",api:"v1"},200,origin);
 if(req.method==="GET"&&path==="/api/v1/pipelines")return json({items:PIPELINES.map(id=>({id,name:id.split("-").map(part=>part.charAt(0).toUpperCase()+part.slice(1)).join(" "),version:"manifest",category:"video",available:true,stages:[]}))},200,origin);

 const auth=req.headers.get("authorization")||"",token=auth.match(/^Bearer\s+(.+)$/i)?.[1];if(!token)return fail("Authentication required",401,origin);
 const sb=createClient(SUPABASE_URL,SUPABASE_ANON_KEY,{auth:{persistSession:false,autoRefreshToken:false},global:{headers:{Authorization:`Bearer ${token}`}}});
 const {data:authData,error:authError}=await sb.auth.getUser(token);if(authError||!authData.user)return fail("Invalid or expired access token",401,origin);
 try{
  if(req.method==="GET"&&path==="/api/v1/pipelines")return json({items:PIPELINES.map(id=>({id,name:id.replaceAll("-"," ").replace(/\b\w/g,m=>m.toUpperCase()),version:"manifest",category:"video",available:true,stages:[]}))},200,origin);
  if(req.method==="GET"&&path==="/api/v1/projects"){const {data,error}=await sb.from("projects").select("id,name,brief,pipeline_id,aspect_ratio,created_at,updated_at").order("created_at",{ascending:false});if(error)throw error;return json({items:data||[]},200,origin);}
  if(req.method==="POST"&&path==="/api/v1/projects"){const b=await req.json(),name=String(b.name||"").trim(),brief=String(b.brief||"").trim(),pipeline_id=String(b.pipeline_id||""),aspect_ratio=b.aspect_ratio||"16:9";if(name.length<1||name.length>120||brief.length<1||brief.length>12000||!PIPELINES.includes(pipeline_id)||!validAspect(aspect_ratio))return fail("Invalid project fields",422,origin);const {data,error}=await sb.from("projects").insert({owner_id:authData.user.id,name,brief,pipeline_id,aspect_ratio}).select("*").single();if(error)throw error;return json(data,201,origin);}
  if(req.method==="GET"&&path==="/api/v1/jobs"){const {data,error}=await sb.from("jobs").select("id,project_id,pipeline_id,status,progress,stage,error_code,created_at,started_at,finished_at").order("created_at",{ascending:false}).limit(100);if(error)throw error;return json({items:data||[]},200,origin);}
  const pj=path.match(/^\/api\/v1\/projects\/([0-9a-f-]+)\/jobs$/i);
  if(pj&&req.method==="GET"){const {data,error}=await sb.from("jobs").select("*").eq("project_id",pj[1]).order("created_at",{ascending:false});if(error)throw error;return json({items:data||[]},200,origin);}
  if(pj&&req.method==="POST"){const {data:p,error:pe}=await sb.from("projects").select("id,pipeline_id").eq("id",pj[1]).maybeSingle();if(pe)throw pe;if(!p)return fail("Project not found",404,origin);const b=await req.json().catch(()=>({})),options=b.options&&typeof b.options==="object"&&!Array.isArray(b.options)?b.options:{};const {data,error}=await sb.from("jobs").insert({owner_id:authData.user.id,project_id:p.id,pipeline_id:p.pipeline_id,status:"queued",payload:options}).select("*").single();if(error)throw error;return json(data,202,origin);}
  const upload=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/uploads$/i);
  if(upload&&req.method==="POST"){
   const {data:job,error:je}=await sb.from("jobs").select("id").eq("id",upload[1]).maybeSingle();if(je)throw je;if(!job)return fail("Job not found",404,origin);
   const b=await req.json(),filename=String(b.filename||"").split(/[\\/]/).pop()!.replace(/[^a-zA-Z0-9._-]/g,"_").slice(0,100),contentType=String(b.content_type||"application/octet-stream"),size=Number(b.size_bytes);
   const allowed=contentType.startsWith("image/")||contentType.startsWith("video/")||contentType.startsWith("audio/")||["application/pdf","text/plain","application/zip"].includes(contentType);
   if(!filename||!allowed||!Number.isSafeInteger(size)||size<1||size>524288000)return fail("Unsupported file or file exceeds 500 MB",422,origin);
   const objectPath=`${authData.user.id}/${upload[1]}/${crypto.randomUUID()}-${filename}`;
   const {data:signed,error:se}=await sb.storage.from(BUCKET).createSignedUploadUrl(objectPath,{upsert:false});if(se)throw se;
   const {data:artifact,error:ae}=await sb.from("job_artifacts").insert({job_id:upload[1],owner_id:authData.user.id,bucket_id:BUCKET,object_path:objectPath,artifact_type:"input",content_type:contentType,size_bytes:size}).select("*").single();if(ae)throw ae;
   return json({artifact, bucket:BUCKET, path:objectPath, token:signed.token, signedUrl:signed.signedUrl},201,origin);
  }
  const artifacts=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/artifacts$/i);
  if(artifacts&&req.method==="GET"){
   const {data:rows,error}=await sb.from("job_artifacts").select("id,job_id,artifact_type,content_type,size_bytes,object_path,created_at").eq("job_id",artifacts[1]).order("created_at",{ascending:false});if(error)throw error;
   const items=[];for(const item of rows||[]){const {data:signed}=await sb.storage.from(BUCKET).createSignedUrl(item.object_path,3600);items.push({...item,signedUrl:signed?.signedUrl||null});}
   return json({items},200,origin);
  }
  const stream=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/events\/stream$/i);
  if(stream&&req.method==="GET"){
   const jobId=stream[1];
   const {data:owned,error:oe}=await sb.from("jobs").select("id").eq("id",jobId).maybeSingle();
   if(oe)throw oe;
   if(!owned)return fail("Job not found",404,origin);
   let cursor=parseLastEventId(req.headers.get("last-event-id"));
   let cancelled=false;
   const encoder=new TextEncoder();
   const body=new ReadableStream<Uint8Array>({
    start(controller){
     const pump=async()=>{
      const deadline=Date.now()+20000;
      try{
       while(!cancelled&&!req.signal.aborted&&Date.now()<deadline){
        const {data,error}=await sb.from("job_events").select("sequence,event_type,stage,progress,message,data,created_at").eq("job_id",jobId).gt("sequence",cursor).order("sequence",{ascending:true}).limit(100);
        if(error)throw error;
        for(const item of data||[]){
         cursor=Math.max(cursor,Number(item.sequence)||0);
         controller.enqueue(encoder.encode(formatSseEvent(item)));
        }
        if(!data?.length)controller.enqueue(encoder.encode(": keep-alive\n\n"));
        await new Promise(resolve=>setTimeout(resolve,1000));
       }
      }catch{
       if(!cancelled&&!req.signal.aborted){
        try{controller.enqueue(encoder.encode("event: stream_error\ndata: {}\n\n"));}catch{}
       }
      }finally{
       try{controller.close();}catch{}
      }
     };
     void pump();
    },
    cancel(){cancelled=true;}
   });
   return new Response(body,{status:200,headers:{...cors(origin),"Content-Type":"text/event-stream; charset=utf-8","Cache-Control":"no-cache, no-transform","X-Accel-Buffering":"no"}});
  }
  const ev=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/events$/i);
  if(ev&&req.method==="GET"){const after=Math.max(0,Number(url.searchParams.get("after")||0));const {data,error}=await sb.from("job_events").select("sequence,event_type,stage,progress,message,data,created_at").eq("job_id",ev[1]).gt("sequence",after).order("sequence",{ascending:true}).limit(500);if(error)throw error;return json({items:data||[]},200,origin);}
  const cancel=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)\/cancel$/i);
  if(cancel&&req.method==="POST"){const {data,error}=await sb.rpc("request_openmontage_job_cancel",{p_job_id:cancel[1]});if(error)throw error;if(!data?.length)return fail("Job is not cancellable or is not accessible",409,origin);return json(data[0],200,origin);}
  const job=path.match(/^\/api\/v1\/jobs\/([0-9a-f-]+)$/i);
  if(job&&req.method==="GET"){const {data,error}=await sb.from("jobs").select("*").eq("id",job[1]).maybeSingle();if(error)throw error;if(!data)return fail("Job not found",404,origin);return json(data,200,origin);}
  return fail("Route not found",404,origin);
 }catch(error){console.error("OpenMontage Edge API failed",error instanceof Error?error.message:"unknown");return fail("Request could not be completed",500,origin);}
});