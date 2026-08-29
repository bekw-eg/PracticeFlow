import type { AxiosResponse } from "axios";
import { api } from "./api";

export const DEFAULT_PAGE_SIZE = 25;

export interface PaginationParams {
  offset: number;
  limit?: number;
  q?: string;
}

export interface PaginationInfo {
  offset: number;
  limit: number;
  total: number;
  hasMore: boolean;
}

export interface Paginated<T> extends PaginationInfo {
  items: T[];
}

export interface PaginatedResource<T> {
  data: T;
  pagination: PaginationInfo;
}

function nonNegativeInteger(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback;
}

function header(headers: AxiosResponse["headers"], name: string): string | undefined {
  const value = headers[name] ?? headers[name.toLowerCase()];
  return Array.isArray(value) ? value[0] : value;
}

export function paginationFromResponse(response: AxiosResponse<unknown>, requested: PaginationParams, returned: number): PaginationInfo {
  const limit = nonNegativeInteger(header(response.headers, "x-limit"), requested.limit ?? DEFAULT_PAGE_SIZE) || DEFAULT_PAGE_SIZE;
  const offset = nonNegativeInteger(header(response.headers, "x-offset"), requested.offset);
  const total = nonNegativeInteger(header(response.headers, "x-total-count"), offset + returned);
  const hasMoreHeader = header(response.headers, "x-has-more");
  return {
    offset,
    limit,
    total,
    // Fall back gracefully while an older backend is being rolled out.
    hasMore: hasMoreHeader === undefined ? returned === limit : hasMoreHeader.toLowerCase() === "true",
  };
}

export function withPagination(path: string, { offset, limit = DEFAULT_PAGE_SIZE, q }: PaginationParams): string {
  const [pathname, existing = ""] = path.split("?", 2);
  const params = new URLSearchParams(existing);
  params.set("offset", String(Math.max(0, offset)));
  params.set("limit", String(limit));
  if (q?.trim()) params.set("q", q.trim());
  else params.delete("q");
  return `${pathname}?${params.toString()}`;
}

export async function fetchPage<T>(path: string, requested: PaginationParams): Promise<Paginated<T>> {
  const response = await api.get<T[]>(withPagination(path, requested));
  return { items: response.data, ...paginationFromResponse(response, requested, response.data.length) };
}

export async function fetchPaginatedResource<T>(path: string, requested: PaginationParams): Promise<PaginatedResource<T>> {
  const response = await api.get<T>(withPagination(path, requested));
  return { data: response.data, pagination: paginationFromResponse(response, requested, 0) };
}
