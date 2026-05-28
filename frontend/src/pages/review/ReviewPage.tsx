import { Typography } from 'antd'

const { Title } = Typography

export default function ReviewPage() {
  return (
    <div className="min-h-screen bg-neutral-bg text-white flex flex-col items-center justify-center p-8">
      <Title level={2} style={{ color: 'white' }}>
        PRism
      </Title>
      <p className="text-gray-400">AI-Powered PR Review Assistant</p>
    </div>
  )
}
