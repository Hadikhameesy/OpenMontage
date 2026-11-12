import { MAX_UPLOAD_BYTES, validateUpload } from "./upload_validation.ts";

Deno.test("accepts supported media below the worker limit", () => {
  if (!validateUpload("scene.png", "image/png", 1024)) throw new Error("valid image rejected");
});

Deno.test("accepts exactly 256 MiB", () => {
  if (!validateUpload("scene.mp4", "video/mp4", MAX_UPLOAD_BYTES)) throw new Error("boundary size rejected");
});

Deno.test("rejects files larger than the worker limit", () => {
  if (validateUpload("scene.mp4", "video/mp4", MAX_UPLOAD_BYTES + 1)) throw new Error("oversized file accepted");
});

Deno.test("rejects empty, unsafe, and unsupported uploads", () => {
  if (validateUpload("", "image/png", 10)) throw new Error("empty filename accepted");
  if (validateUpload("x.bin", "application/octet-stream", 10)) throw new Error("unsupported type accepted");
  if (validateUpload("x.png", "image/png", 0)) throw new Error("empty file accepted");
  if (validateUpload("x.png", "image/png", 1.5)) throw new Error("non-integer size accepted");
});
