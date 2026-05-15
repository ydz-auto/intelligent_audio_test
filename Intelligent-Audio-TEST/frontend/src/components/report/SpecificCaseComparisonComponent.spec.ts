import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SpecificCaseComparisonComponent from './SpecificCaseComparisonComponent.vue'

describe('SpecificCaseComparisonComponent', () => {
  it('renders case cards from camelCase detailedResults', () => {
    const wrapper = mount(SpecificCaseComparisonComponent, {
      props: {
        reportData: {
          detailedResults: [
            {
              testCaseId: 123,
              testCaseName: '用例A',
              testCaseGroup: { name: '分组1' },
              testCaseTags: [{ name: 'tag1' }],
              status: '已完成',
              createdAt: 1700000000,
              device: { id: 1, name: '设备1' },
              asr: { referenceText: 'ref', resultText: 'hyp' },
              translation: { referenceText: 'refT', resultText: 'hypT' },
              dimensionScores: [{ dimensionName: 'WER', score: 0.1 }]
            }
          ]
        }
      },
      global: {
        stubs: {
          AudioPlayerModal: true,
          TestCaseReportDetail: true
        }
      }
    })

    expect(wrapper.text()).toContain('具体用例对比')
    expect(wrapper.text()).toContain('用例A')
    expect(wrapper.text()).toContain('分组1')
  })
})

