export type WorkflowStage = "upload" | "mask" | "matting" | "review" | "background" | "done";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface ProjectFiles {
  video?: string | null;
  background?: string | null;
  first_frame?: string | null;
  subject_mask?: string | null;
  subject_overlay?: string | null;
  final_mask?: string | null;
  final_overlay?: string | null;
  foreground_masks?: string[];
  foreground_overlays?: string[];
  retained_masks?: Array<{
    id?: string | null;
    name?: string | null;
    mask?: string | null;
    overlay?: string | null;
    source?: Record<string, unknown>;
  }>;
  alpha?: string | null;
  foreground?: string | null;
  green?: string | null;
  replaced?: string | null;
  round_count?: number;
}

export interface ProjectState {
  subject_mask?: string | null;
  foreground_masks?: string[];
  retained_masks?: Array<{
    id?: string;
    name?: string;
    mask?: string;
    overlay?: string;
    source?: Record<string, unknown>;
  }>;
  final_mask?: string | null;
  history?: Array<{
    action: string;
    payload?: Record<string, unknown>;
    time?: string;
  }>;
}

export interface ProjectResponse {
  project_id: string;
  status: string;
  files: ProjectFiles;
  state: ProjectState;
}

export interface JobResponse {
  job_id: string;
  project_id: string;
  status: JobStatus;
  stage: string;
  progress: number;
  message: string;
  result?: ProjectResponse | null;
  error?: {
    code: string;
    message: string;
  } | null;
}

export interface MattingSettings {
  warmup: number;
  erode: number;
  dilate: number;
  max_size: number;
  save_image: boolean;
}

export interface Point {
  x: number;
  y: number;
}
