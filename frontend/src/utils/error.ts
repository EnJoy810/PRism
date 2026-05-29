import type { AxiosError } from 'axios'
import type { ApiResponse } from './request'

const KNOWN_ERRORS: Record<string, string> = {
  ECONNREFUSED: '无法连接到后端服务，请确认后端已启动（uvicorn app.main:app --reload）',
  ETIMEDOUT: '请求超时，请检查网络连接或稍后重试',
}

export function getApiErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiResponse<unknown>>

  if (axiosError.code && KNOWN_ERRORS[axiosError.code]) {
    return KNOWN_ERRORS[axiosError.code]
  }

  return (
    axiosError?.response?.data?.message ??
    axiosError?.message ??
    '未知错误，请稍后重试'
  )
}
