import { PublicFooter, PublicHeader } from './components/public-shell'
import { ConsoleEntriesSection } from './components/sections/console-entries'
import { CtaBandSection } from './components/sections/cta-band'
import { DataReliabilitySection } from './components/sections/data-reliability'
import { DeploymentTrustSection } from './components/sections/deployment-trust'
import { FaqSection } from './components/sections/faq'
import { HeroSection } from './components/sections/hero'
import { QuickStartSection } from './components/sections/quick-start'
import { TestObjectAccessSection } from './components/sections/test-object-access'
import { WhyChooseUsSection } from './components/sections/why-choose-us'

/**
 * 首页门户落地页（03_首页.md §3.1）：公开页（不进 _authenticated 组），
 * 分区按序垂直堆叠——main 不加 container，分区自管宽度。
 * 自定义首页三态（§3.11）：本平台接口未落，恒走 landing（TODO(API 接线)）。
 * ⑤ 接入测试对象（INT-420：被测设备/被测APP/被测API 三对象卡 + 接入演示三页签）。
 */
export default function Home() {
  return (
    <div className='bg-background min-h-svh'>
      <PublicHeader />
      <main>
        <HeroSection />
        <QuickStartSection />
        <WhyChooseUsSection />
        <ConsoleEntriesSection />
        <TestObjectAccessSection />
        <DataReliabilitySection />
        <DeploymentTrustSection />
        <FaqSection />
        <CtaBandSection />
      </main>
      <PublicFooter />
    </div>
  )
}
