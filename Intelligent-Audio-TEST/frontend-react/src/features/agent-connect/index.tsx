/**
 * 连接你的 agent 入口页（features/agent-connect，INT-1153/INT-1140 方案 2）。
 * 登录壳内页面：使用说明 / skill 服务地址配置（默认取浏览器地址栏、可编辑）/
 * Access Token 指引（跳 /profile）/ 炫彩「下载 skill」按钮。
 * 下载走真实接口 GET /api/v1/agent/skill?base_url=…（accessTokenApi.downloadSkill），
 * URL 作为查询参数注入后端模板，无 mock 残留。
 */
import { Link } from '@tanstack/react-router'
import { BookOpen, Download, KeyRound, Link2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useSkillDownload } from '@/application/access-token/use-skill-download'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { IconBadge } from '@/components/ui/icon-badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
  AGENT_CONNECT_DOWNLOAD_ARIA,
  AGENT_CONNECT_DOWNLOAD_BUTTON,
  AGENT_CONNECT_DOWNLOAD_SUCCESS,
  AGENT_CONNECT_DOWNLOAD_TITLE,
  AGENT_CONNECT_DOWNLOADING,
  AGENT_CONNECT_PAGE_DESCRIPTION,
  AGENT_CONNECT_PAGE_TITLE,
  AGENT_CONNECT_STEPS,
  AGENT_CONNECT_TOKEN_DESCRIPTION,
  AGENT_CONNECT_TOKEN_GO_PROFILE,
  AGENT_CONNECT_TOKEN_TITLE,
  AGENT_CONNECT_URL_DESCRIPTION,
  AGENT_CONNECT_URL_PLACEHOLDER,
  AGENT_CONNECT_URL_TITLE,
  AGENT_CONNECT_URL_VALIDATE_ERROR,
  AGENT_CONNECT_USAGE_DESCRIPTION,
  AGENT_CONNECT_USAGE_TITLE,
} from './constants'

const URL_PATTERN = /^https?:\/\/.+/i

function defaultBaseUrl(): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return origin || ''
}

export function AgentConnectPage() {
  useEffect(() => {
    document.title = AGENT_CONNECT_PAGE_TITLE
  }, [])

  const { downloading, error, download } = useSkillDownload()
  const [baseUrl, setBaseUrl] = useState(() => defaultBaseUrl())
  const [touched, setTouched] = useState(false)
  const urlValid = URL_PATTERN.test(baseUrl)
  const showUrlError = touched && !urlValid

  const steps = useMemo(() => AGENT_CONNECT_STEPS, [])

  const handleDownload = async () => {
    setTouched(true)
    if (!urlValid) return
    const ok = await download(baseUrl)
    if (ok) toast.success(AGENT_CONNECT_DOWNLOAD_SUCCESS)
  }

  return (
    <SectionPageLayout>
      <SectionPageLayout.Title>{AGENT_CONNECT_PAGE_TITLE}</SectionPageLayout.Title>
      <SectionPageLayout.Content>
        <div className='mx-auto grid w-full max-w-3xl gap-4'>
          <p className='text-muted-foreground text-sm'>{AGENT_CONNECT_PAGE_DESCRIPTION}</p>

          {/* 使用说明 */}
          <Card>
            <CardHeader>
              <div className='flex items-center gap-2.5'>
                <IconBadge tone='info' size='sm' decorative>
                  <BookOpen aria-hidden='true' />
                </IconBadge>
                <div className='grid gap-0.5'>
                  <CardTitle className='text-sm'>{AGENT_CONNECT_USAGE_TITLE}</CardTitle>
                  <CardDescription className='text-xs sm:text-sm'>
                    {AGENT_CONNECT_USAGE_DESCRIPTION}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className='grid gap-3'>
              {steps.map((step, index) => (
                <div key={step.key} className='flex items-start gap-3'>
                  <span className='bg-primary text-primary-foreground mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-medium'>
                    {index + 1}
                  </span>
                  <div className='grid gap-0.5'>
                    <p className='text-sm font-medium'>{step.title}</p>
                    <p className='text-muted-foreground text-xs sm:text-sm'>
                      {step.description}
                      {step.link && (
                        <Link
                          to={step.link}
                          className='text-primary hover:underline'
                        >
                          {step.linkLabel}
                        </Link>
                      )}
                    </p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Skill 服务地址 */}
          <Card>
            <CardHeader>
              <div className='flex items-center gap-2.5'>
                <IconBadge tone='neutral' size='sm' decorative>
                  <Link2 aria-hidden='true' />
                </IconBadge>
                <div className='grid gap-0.5'>
                  <CardTitle className='text-sm'>{AGENT_CONNECT_URL_TITLE}</CardTitle>
                  <CardDescription className='text-xs sm:text-sm'>
                    {AGENT_CONNECT_URL_DESCRIPTION}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className='grid gap-2'>
              <Label htmlFor='agent-connect-base-url'>服务地址</Label>
              <Input
                id='agent-connect-base-url'
                value={baseUrl}
                placeholder={AGENT_CONNECT_URL_PLACEHOLDER}
                onChange={(event) => setBaseUrl(event.target.value.trim())}
                aria-invalid={showUrlError}
              />
              {showUrlError && (
                <p className='text-destructive text-sm'>{AGENT_CONNECT_URL_VALIDATE_ERROR}</p>
              )}
            </CardContent>
          </Card>

          {/* Access Token 指引 */}
          <Card>
            <CardHeader>
              <div className='flex items-center gap-2.5'>
                <IconBadge tone='warning' size='sm' decorative>
                  <KeyRound aria-hidden='true' />
                </IconBadge>
                <div className='grid gap-0.5'>
                  <CardTitle className='text-sm'>{AGENT_CONNECT_TOKEN_TITLE}</CardTitle>
                  <CardDescription className='text-xs sm:text-sm'>
                    {AGENT_CONNECT_TOKEN_DESCRIPTION}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Button type='button' variant='outline' size='sm' render={<Link to='/profile' />}>
                {AGENT_CONNECT_TOKEN_GO_PROFILE}
              </Button>
            </CardContent>
          </Card>

          {/* 下载 skill */}
          <Card>
            <CardHeader>
              <div className='flex items-center gap-2.5'>
                <IconBadge tone='info' size='sm' decorative>
                  <Download aria-hidden='true' />
                </IconBadge>
                <div className='grid gap-0.5'>
                  <CardTitle className='text-sm'>{AGENT_CONNECT_DOWNLOAD_TITLE}</CardTitle>
                  <CardDescription className='text-xs sm:text-sm'>
                    使用上方服务地址生成 skill 包（SKILL.md + MCP 配置模板）。
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className='grid gap-3'>
              <button
                type='button'
                data-slot='button'
                aria-label={AGENT_CONNECT_DOWNLOAD_ARIA}
                disabled={downloading}
                onClick={() => void handleDownload()}
                className='ai-discount-core relative isolate h-10 shrink-0 cursor-pointer rounded-full border-0 px-5 font-bold text-white transition-all hover:brightness-110 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
              >
                <span className='ai-discount-word inline-flex items-center justify-center gap-2'>
                  <Download aria-hidden='true' className='size-4' />
                  {downloading ? AGENT_CONNECT_DOWNLOADING : AGENT_CONNECT_DOWNLOAD_BUTTON}
                </span>
              </button>
              {error && (
                <Alert variant='destructive'>
                  <AlertDescription className='text-xs'>{error}</AlertDescription>
                </Alert>
              )}
              {!urlValid && touched && !error && (
                <Alert variant='destructive'>
                  <AlertDescription className='text-xs'>
                    {AGENT_CONNECT_URL_VALIDATE_ERROR}
                  </AlertDescription>
                </Alert>
              )}
              {!urlValid && !touched && (
                <Alert variant='default'>
                  <AlertDescription className='text-xs'>
                    请确认服务地址为 http(s) 开头，再下载 skill 包。
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
