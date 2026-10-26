<#
INT-1276 / INT-181：两个演示地址（React 15173 / 新 Vue 16173）的静态托管部署脚本。

背景：演示地址早期跑的是 `rsbuild dev` / `vite dev`（未压缩、每模块一个请求、no-cache）。
本脚本把 **build 产物** 打进 nginx 镜像托管，并带 `docker/nginx-frontend.conf` 的
gzip + 分级缓存（static/assets 一年 immutable，index.html no-cache）。

用法（只从 docker 目录操作；一次只部署一次，不要反复重启）：
    # 默认从演示分支的 build 产物部署
    pwsh -File deploy_demo_frontends.ps1
    # 只刷一边 / 指定产物目录（例如从运行中容器里冻结现有内容）
    pwsh -File deploy_demo_frontends.ps1 -SkipVue -ReactDist D:\tmp\react-html

约定：脚本用固定容器名 / 端口 / 网络，可重复执行（幂等：重建镜像并重建容器）。
<#>
param(
  [string]$ReactDist = "D:\00_code\V9.7.31-UX\Intelligent-Audio-TEST\frontend-react\dist",
  [string]$VueDist   = "D:\00_code\V9.7.31-WIRING-UXVUE\Intelligent-Audio-TEST\frontend\dist",
  [string]$Conf      = "",
  [string]$Network   = "intelligent-audio-test_default",
  [switch]$SkipReact,
  [switch]$SkipVue
)

$ErrorActionPreference = 'Stop'
if (-not $Conf) { $Conf = Join-Path $PSScriptRoot 'nginx-frontend.conf' }
if (-not (Test-Path $Conf)) { throw "nginx 配置不存在: $Conf" }

function Deploy-Frontend {
  param([string]$Name, [string]$Dist, [string]$Image, [int]$Port)

  if (-not (Test-Path (Join-Path $Dist 'index.html'))) {
    throw "[$Name] 产物目录里没有 index.html，不是 build 产物: $Dist"
  }

  $stage = Join-Path ([System.IO.Path]::GetTempPath()) "int1276-$Name"
  if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
  New-Item -ItemType Directory -Path $stage | Out-Null
  Copy-Item -Recurse $Dist (Join-Path $stage 'dist')
  Copy-Item $Conf (Join-Path $stage 'nginx-frontend.conf')
  @'
FROM nginx:alpine
COPY nginx-frontend.conf /etc/nginx/conf.d/default.conf
COPY dist/ /usr/share/nginx/html/
EXPOSE 80
'@ | Set-Content -Path (Join-Path $stage 'Dockerfile') -Encoding utf8

  Write-Host "[$Name] build $Image from $Dist"
  docker build -q -t $Image $stage | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "[$Name] docker build 失败" }

  docker rm -f $Name 2>$null | Out-Null
  docker run -d --name $Name --network $Network -p "${Port}:80" $Image | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "[$Name] docker run 失败" }

  for ($i = 0; $i -lt 30; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/" -TimeoutSec 3
      if ($r.StatusCode -eq 200) { Write-Host "[$Name] up on :$Port"; return }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  throw "[$Name] 30s 内 :$Port 未就绪"
}

if (-not $SkipReact) { Deploy-Frontend -Name 'iat-react-frontend' -Dist $ReactDist -Image 'iat-react-frontend:latest' -Port 15173 }
if (-not $SkipVue)   { Deploy-Frontend -Name 'iat-uxvue-frontend' -Dist $VueDist   -Image 'iat-uxvue-frontend:latest' -Port 16173 }

Write-Host "完成。验收：curl -sI -H 'Accept-Encoding: gzip, br' http://localhost:15173/static/... "
