import type { JobResponse, MattingSettings, Point, ProjectResponse } from "./types";

type ProgressHandler = (progress: number) => void;

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }
  return data as T;
}

export async function requestJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options);
  return parseResponse<T>(response);
}

function uploadJson<T>(
  url: string,
  formData: FormData,
  onProgress?: ProgressHandler,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "text";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(event.loaded / event.total);
      }
    };
    xhr.onload = () => {
      try {
        const payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(JSON.stringify(payload, null, 2)));
          return;
        }
        resolve(payload as T);
      } catch (error) {
        reject(error);
      }
    };
    xhr.onerror = () => reject(new Error("网络请求失败"));
    xhr.send(formData);
  });
}

export function uploadVideoProject(
  projectId: string,
  video: File,
  onProgress?: ProgressHandler,
): Promise<ProjectResponse> {
  const formData = new FormData();
  formData.append("project_id", projectId);
  formData.append("video", video);
  return uploadJson<ProjectResponse>("/api/projects", formData, onProgress);
}

export function uploadBackground(
  projectId: string,
  background: File,
  onProgress?: ProgressHandler,
): Promise<JobResponse> {
  const formData = new FormData();
  formData.append("background", background);
  return uploadJson<JobResponse>(`/api/projects/${projectId}/background`, formData, onProgress);
}

export function postJson<T>(url: string, payload: unknown = {}): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getHealth(): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/health");
}

export function getProject(projectId: string): Promise<ProjectResponse> {
  return requestJson<ProjectResponse>(`/api/projects/${projectId}`);
}

export function addMaskText(projectId: string, text: string): Promise<ProjectResponse> {
  return postJson<ProjectResponse>(`/api/projects/${projectId}/masks/text`, { text });
}

export function addMaskPoint(projectId: string, point: Point): Promise<ProjectResponse> {
  return postJson<ProjectResponse>(`/api/projects/${projectId}/masks/point`, {
    point: [point.x, point.y],
  });
}

export function addMaskBox(projectId: string, box: [number, number, number, number]): Promise<ProjectResponse> {
  return postJson<ProjectResponse>(`/api/projects/${projectId}/masks/box`, { box });
}

export function undoMask(projectId: string): Promise<ProjectResponse> {
  return postJson<ProjectResponse>(`/api/projects/${projectId}/mask/undo`);
}

export function clearMasks(projectId: string): Promise<ProjectResponse> {
  return postJson<ProjectResponse>(`/api/projects/${projectId}/masks/clear`);
}

export function startMatting(
  projectId: string,
  settings: MattingSettings,
): Promise<JobResponse> {
  return postJson<JobResponse>(`/api/projects/${projectId}/matting`, settings);
}

export function getJob(jobId: string): Promise<JobResponse> {
  return requestJson<JobResponse>(`/api/jobs/${jobId}`);
}

export function fileUrl(url?: string | null): string | undefined {
  if (!url) return undefined;
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
}
