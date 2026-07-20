/**
 * API 通用类型 — N6 前端类型清理
 *
 * 后端 FastAPI 返回的标准格式（参考 backend/api/*.py 的 JSONResponse）。
 */

/** 标准 API 响应（成功） */
export interface ApiResponse<T = unknown> {
  success?: boolean;
  data?: T;
  error?: string;
  message?: string;
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** 通用错误（catch 块） */
export interface ApiError {
  message: string;
  status?: number;
  detail?: unknown;
}

/** 把 unknown 收窄为 ApiError 的类型守卫 */
export function asApiError(e: unknown): ApiError {
  if (e instanceof Error) {
    return { message: e.message };
  }
  if (typeof e === "object" && e !== null && "message" in e) {
    return { message: String((e as { message: unknown }).message) };
  }
  return { message: String(e) };
}
