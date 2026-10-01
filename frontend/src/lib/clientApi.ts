type ApiRequestOptions = {
  params?: Record<string, string | number | boolean | null | undefined>;
  responseType?: "json" | "blob";
};

type ApiResponse<T> = { data: T };

export class ClientApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly data: unknown,
  ) {
    super(message);
    this.name = "ClientApiError";
  }
}

function requestUrl(path: string, params?: ApiRequestOptions["params"]) {
  const url = new URL(path, window.location.origin);
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<T>> {
  const isFormData = body instanceof FormData;
  const token = window.sessionStorage.getItem("hodi_api_token");
  const headers = new Headers();
  if (token) headers.set("Authorization", `Token ${token}`);
  if (body !== undefined && !isFormData) headers.set("Content-Type", "application/json");
  const response = await fetch(requestUrl(path, options.params), {
    method,
    credentials: "same-origin",
    headers,
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const details = payload && typeof payload === "object"
      ? payload as Record<string, unknown>
      : {};
    const message =
      (typeof details.detail === "string" && details.detail) ||
      (typeof details.error === "string" && details.error) ||
      `Request failed (${response.status}).`;
    throw new ClientApiError(message, response.status, payload);
  }

  if (options.responseType === "blob") {
    return { data: await response.blob() as T };
  }
  if (response.status === 204) return { data: undefined as T };
  return { data: await response.json() as T };
}

export const clientApi = {
  get<T>(path: string, options?: ApiRequestOptions) {
    return request<T>("GET", path, undefined, options);
  },
  post<T = unknown>(path: string, body?: unknown, options?: ApiRequestOptions) {
    return request<T>("POST", path, body, options);
  },
  patch<T = unknown>(path: string, body?: unknown, options?: ApiRequestOptions) {
    return request<T>("PATCH", path, body, options);
  },
};
