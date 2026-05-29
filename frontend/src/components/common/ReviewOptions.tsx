import { Collapse, Switch, Slider, Typography } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import { useReviewOptions } from '../../stores/reviewOptions'

const { Text } = Typography

export default function ReviewOptions() {
  const { options, setIncludeStyle, setContextLines } = useReviewOptions()

  return (
    <Collapse
      ghost
      className="w-full max-w-2xl mt-2"
      style={{ border: 'none' }}
      items={[
        {
          key: 'options',
          label: (
            <div className="flex items-center gap-2 text-gray-400">
              <SettingOutlined />
              <Text className="text-gray-400 text-sm">Review 选项</Text>
            </div>
          ),
          children: (
            <div className="space-y-4 px-1">
              <div className="flex items-center justify-between">
                <div>
                  <Text className="text-gray-300 text-sm block">包含风格问题（INFO）</Text>
                  <Text className="text-gray-500 text-xs">默认仅显示 ERROR 和 WARNING</Text>
                </div>
                <Switch
                  checked={options.includeStyle}
                  onChange={setIncludeStyle}
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <Text className="text-gray-300 text-sm">上下文行数</Text>
                  <Text className="text-gray-500 text-xs">{options.contextLines} 行</Text>
                </div>
                <Slider
                  min={0}
                  max={10}
                  value={options.contextLines}
                  onChange={setContextLines}
                  className="w-full"
                />
              </div>
            </div>
          ),
        },
      ]}
    />
  )
}
