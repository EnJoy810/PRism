import axios from 'axios'

export interface ApiResponse<T> {
  code: string
  message: string
  data: T
}

const request = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

request.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
)

export default request
