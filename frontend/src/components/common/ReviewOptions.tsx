import { Collapse, Segmented, Switch, Slider, Typography } from 'antd'
import { SettingOutlined, SafetyCertificateOutlined, ThunderboltOutlined, CodeOutlined, EyeOutlined } from '@ant-design/icons'
import { useReviewOptions, PERSPECTIVE_LABELS, type Perspective } from '../../stores/reviewOptions'

const { Text } = Typography

const PERSPECTIVE_ICONS: Record<Perspective, React.ReactNode> = {
  default: <EyeOutlined />,
  security: <SafetyCertificateOutlined />,
  performance: <ThunderboltOutlined />,
  maintainability: <CodeOutlined />,
}

export default function ReviewOptions() {
  const { options, setIncludeStyle, setContextLines, setPerspective } = useReviewOptions()

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
              <div>
                <Text className="text-gray-300 text-sm block mb-2">审查视角</Text>
                <Segmented
                  value={options.perspective}
                  onChange={(v) => setPerspective(v as Perspective)}
                  options={(['default', 'security', 'performance', 'maintainability'] as Perspective[]).map((p) => ({
                    value: p,
                    label: (
                      <span className="flex items-center gap-1.5 text-xs">
                        {PERSPECTIVE_ICONS[p]}
                        {PERSPECTIVE_LABELS[p]}
                      </span>
                    ),
                  }))}
                  className="w-full"
                />
              </div>
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
