import type { AxiosError } from 'axios'
import type { ApiResponse } from './request'

export function getApiErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiResponse<unknown>>
  return (
    axiosError?.response?.data?.message ??
    axiosError?.message ??
    'An unexpected error occurred'
  )
}
