import { createBrowserRouter } from 'react-router-dom'
import ReviewPage from '../pages/review/ReviewPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ReviewPage />,
  },
])
