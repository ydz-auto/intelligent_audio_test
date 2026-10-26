<#
INT-1276 / INT-181 / INT-2012：两个演示地址（React 15173 / 新 Vue 16173）的静态托管部署脚本。

背景：演示地址早期跑的是 `rsbuild dev` / `vite dev`（未压缩、每模块一个请求、no-cache）。
本脚本把 **build 产物** 打进 nginx 镜像托管，并带 `docker/nginx-frontend.conf` 的
gzip + 分级缓存（static/assets 一年 immutable，index.html no-cache）。

口径（INT-2012，2026-10-26 方案 A）：**15173 的产物来源唯一 = `wiring/react` 产品演示**。
`design/ux-redesign` 是视觉稿分支（任务域导入导出等只有占位实现、落后接线分支数百个提交），
刷到 15173 会让负责人「功能消失」，所以脚本内置**产物来源硬门禁**：React dist 必须命中
产品标记 `连接你的 agent`，且不得命中占位串 `导出流程见导出数据弹窗`，否则拒绝部署。
设计/性能观感（E1/E2/E4 图表收敛、字体瘦身）另址或本地 build 取数，不再刷 15173。

用法（只从部署 clone 的 docker 目录操作；一次只部署一次，不要反复重启）：
    # 默认从演示分支（wiring/react · wiring/ux-vue）的 build 产物部署
    pwsh -File deploy_demo_frontends.ps1
    # 只刷一边 / 指定产物目录（例如从运行中容器里冻结现有内容）
    pwsh -File deploy_demo_frontends.ps1 -SkipVue -ReactDist D:\tmp\react-html

护栏（INT-2012）：
  1. 来源门禁：不符合上面口径的 dist 直接 throw，退出码非 0；`-AllowAnyDist` 显式绕过，
     绕过时打醒目告警并记录 dist 路径与构建时间。
  2. 部署锁 `docker/.deploy.lock`：已有部署在跑时第二个进程**立即失败**并打印持锁 PID / 开始时间，
     不排队、不覆盖（进程已退出的过期锁自动接管）。
  3. 先校验两边、再一起部署：任一边校验证失败，两边都不动。
  4. 部署后自检 + 回滚：重建前给当前 `latest` 打回滚 tag；起容器后自检 `GET /` 200、
     容器 index.html 引用的 chunk 与 dist 一致、每个 chunk 文件在容器内存在、
     容器内 async 数量 == dist 内数量；任一失败自动回滚旧镜像并 exit 1。
  5. `-FaultInject missing-chunk` 仅用于演练自检失败路径（从构建上下文删一个 async chunk）。
  6. `-DryRun` 只做来源门禁与产物校验并打印计划，不碰 docker（演练 -AllowAnyDist 时用它，避免真把设计稿刷上去）。

约定：脚本用固定容器名 / 端口 / 网络，可重复执行（幂等：重建镜像并重建容器）。
#>
param(
  [string]$ReactDist = "D:\00_code\V9.7.31-WIRING-REACT\Intelligent-Audio-TEST\frontend-react\dist",
  [string]$VueDist   = "D:\00_code\V9.7.31-WIRING-UXVUE\Intelligent-Audio-TEST\frontend\dist",
  [string]$Conf      = "",
  [string]$Network   = "intelligent-audio-test_default",
  [switch]$SkipReact,
  [switch]$SkipVue,
  [switch]$AllowAnyDist,
  [switch]$DryRun,
  [ValidateSet('', 'missing-chunk')]
  [string]$FaultInject = ""
)

$ErrorActionPreference = 'Stop'
if (-not $Conf) { $Conf = Join-Path $PSScriptRoot 'nginx-frontend.conf' }
if (-not (Test-Path $Conf)) { throw "nginx 配置不存在: $Conf" }

# 产品标记：wiring/react 的「连接你的 agent」入口组件；占位串只在 design/ux-redesign 上出现
# （任务域导入导出还是占位实现，INT-2012 实测 166 个 async / 无 jsencrypt / 无标签来源）。
$ProductMarker   = '连接你的 agent'
$PlaceholderMark = '导出流程见导出数据弹窗'
$MarkerTextGlob  = @('*.js', '*.html', '*.css')

$LockPath        = Join-Path $PSScriptRoot '.deploy.lock'
$script:LockHeld = $false

function Get-DistBuildTime {
  param([string]$Dist)
  try { return (Get-Item (Join-Path $Dist 'index.html')).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss') }
  catch { return 'unknown' }
}

function Test-MarkerInDist {
  param([string]$Dist, [string]$Marker)
  $hit = Get-ChildItem -Path $Dist -Recurse -File -Include $MarkerTextGlob -ErrorAction SilentlyContinue |
    Select-String -Pattern $Marker -SimpleMatch -List -ErrorAction SilentlyContinue |
    Select-Object -First 1
  return [bool]$hit
}

function Get-ChunkRefs {
  param([string]$Html)
  $refs = [regex]::Matches($Html, '/(?:static|assets)/[^"''<>\s]+') | ForEach-Object { $_.Value }
  return @($refs | Sort-Object -Unique)
}

# ---- 部署锁（INT-2012 §2.3）------------------------------------------------
function Acquire-DeployLock {
  for ($attempt = 0; $attempt -lt 2; $attempt++) {
    try {
      # CreateNew 是原子的：并发时第二个进程一定拿到 IOException，不会互相覆盖
      $stream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
      $writer = New-Object System.IO.StreamWriter($stream)
      $writer.WriteLine("pid=$PID")
      $writer.WriteLine("started_utc=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))")
      $writer.WriteLine("host=$env:COMPUTERNAME")
      $writer.WriteLine("react_dist=$ReactDist")
      $writer.Flush()
      $writer.Dispose()
      $stream.Dispose()
      $script:LockHeld = $true
      return
    } catch {
      # .NET 方法失败会被 PS 包成 MethodInvocationException，不能只 catch [System.IO.IOException]
      if (-not (Test-Path $LockPath)) { throw }
      $info = (Get-Content $LockPath -Raw -ErrorAction SilentlyContinue)
      if (-not "$info".Trim()) {
        # 另一个进程刚 CreateNew、内容还没落盘：等一拍再读，避免把活锁当成过期锁接管
        Start-Sleep -Milliseconds 300
        $info = (Get-Content $LockPath -Raw -ErrorAction SilentlyContinue)
      }
      $holderPid = $null
      if ($info -match 'pid=(\d+)') { $holderPid = [int]$Matches[1] }
      if ($holderPid -and (Get-Process -Id $holderPid -ErrorAction SilentlyContinue)) {
        $holderStart = if ($info -match 'started_utc=([^\r\n]+)') { $Matches[1] } else { 'unknown' }
        throw ("[lock] 另一个部署正在进行：PID=$holderPid 开始时间(UTC)=$holderStart。" +
          "本进程立即失败，不排队、不覆盖。锁文件: $LockPath（确认该进程已死可手工删除）")
      }
      if (-not "$info".Trim()) {
        throw "[lock] 部署锁 $LockPath 存在但内容为空且读不出持锁 PID，为避免覆盖，本进程直接退出（确认无部署在跑可手工删除该文件）"
      }
      Write-Warning "[lock] 发现过期部署锁（持有进程 $holderPid 已不在）：$($info -replace '\r?\n', '; ') —— 接管"
      Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
    }
  }
  throw "[lock] 无法获取部署锁: $LockPath"
}

function Release-DeployLock {
  if (-not $script:LockHeld) { return }
  try {
    $info = Get-Content $LockPath -Raw -ErrorAction SilentlyContinue
    if ($info -match "pid=$PID(\D|$)") { Remove-Item $LockPath -Force -ErrorAction SilentlyContinue }
  } catch { }
  $script:LockHeld = $false
}

# ---- 产物校验（先校验，两边都过了才动手）----------------------------------
function Test-Dist {
  param([string]$Name, [string]$Dist, [string]$Kind)

  if (-not (Test-Path (Join-Path $Dist 'index.html'))) {
    throw "[$Name] 产物目录里没有 index.html，不是 build 产物: $Dist"
  }

  $hasProduct   = Test-MarkerInDist -Dist $Dist -Marker $ProductMarker
  $hasPlaceholder = Test-MarkerInDist -Dist $Dist -Marker $PlaceholderMark
  $buildTime    = Get-DistBuildTime -Dist $Dist

  if ($Kind -eq 'react') {
    if (-not ($hasProduct -and -not $hasPlaceholder)) {
      $detail = "命中「$ProductMarker」=$hasProduct，命中占位串「$PlaceholderMark」=$hasPlaceholder"
      if ($AllowAnyDist) {
        Write-Warning ('!' * 78)
        Write-Warning "!! 已用 -AllowAnyDist 绕过产物来源门禁（$detail）"
        Write-Warning "!! dist : $Dist"
        Write-Warning "!! 构建时间: $buildTime"
        Write-Warning ('!' * 78)
      } else {
        throw ("[$Name] 疑似 design/ux-redesign 产物，拒绝部署（$detail）。" +
          "15173 的产物来源唯一 = wiring/react（INT-2012），切换 -ReactDist 到接线分支 dist；" +
          "确需强推请显式加 -AllowAnyDist。dist: $Dist（构建时间 $buildTime）")
      }
    } else {
      Write-Host "[$Name] 来源门禁通过：命中「$ProductMarker」、未命中占位串（dist 构建时间 $buildTime）"
    }
  }

  $html   = Get-Content (Join-Path $Dist 'index.html') -Raw
  $chunks = Get-ChunkRefs -Html $html
  if ($chunks.Count -eq 0) { throw "[$Name] dist/index.html 没有引用任何 static/assets 产物: $Dist" }

  $asyncDir = Join-Path $Dist 'static/js/async'
  $asyncCount = $null
  if (Test-Path $asyncDir) {
    $asyncCount = @(Get-ChildItem $asyncDir -File).Count
  }

  return [pscustomobject]@{
    Name = $Name; Dist = $Dist; Kind = $Kind; BuildTime = $buildTime
    Chunks = $chunks; AsyncCount = $asyncCount
  }
}

# ---- 自检 -----------------------------------------------------------------
function Test-Deployed {
  param([string]$Name, [int]$Port, $Plan)

  $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/" -TimeoutSec 5
  if ($r.StatusCode -ne 200) { throw "[$Name] 自检失败：GET / 返回 $($r.StatusCode)" }

  $html = if ($r.Content -is [byte[]]) { [System.Text.Encoding]::UTF8.GetString($r.Content) } else { [string]$r.Content }
  $got = Get-ChunkRefs -Html $html
  $want = $Plan.Chunks
  $diff = Compare-Object -ReferenceObject $want -DifferenceObject $got
  if ($diff) {
    $missing = ($diff | Where-Object SideIndicator -eq '<=' | ForEach-Object InputObject) -join ', '
    $extra   = ($diff | Where-Object SideIndicator -eq '=>' | ForEach-Object InputObject) -join ', '
    throw "[$Name] 自检失败：index.html 引用 chunk 与 dist 不一致（缺: [$missing] 多: [$extra]）"
  }

  foreach ($c in $want) {
    docker exec $Name sh -c "test -f '/usr/share/nginx/html$c'" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "[$Name] 自检失败：容器内缺少 chunk $c" }
  }

  if ($null -ne $Plan.AsyncCount) {
    $actualRaw = docker exec $Name sh -c 'ls -1 /usr/share/nginx/html/static/js/async | wc -l'
    $actual = [int]("$actualRaw".Trim())
    if ($actual -ne $Plan.AsyncCount) {
      throw "[$Name] 自检失败：容器内 async 数量 $actual != dist 内数量 $($Plan.AsyncCount)"
    }
    Write-Host "[$Name] 自检：async $actual 个（== dist），chunk $(($want).Count) 个全部存在"
  } else {
    Write-Host "[$Name] 自检：chunk $(($want).Count) 个全部存在"
  }
}

# ---- 部署 -----------------------------------------------------------------
function Deploy-Frontend {
  param([string]$Name, [string]$ImageName, [int]$Port, $Plan)

  $image   = "${ImageName}:latest"
  $rollbackTag = "${ImageName}:rollback-" + (Get-Date).ToString('yyyyMMdd-HHmmss')
  $prevImageId = (docker images -q $image 2>$null | Select-Object -First 1)

  if ($prevImageId) {
    docker tag $image $rollbackTag | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "[$Name] 打回滚 tag 失败: $rollbackTag" }
    Write-Host "[$Name] 回滚 tag: $rollbackTag (prev=$prevImageId)"
  } else {
    Write-Warning "[$Name] 没有既有 $image，失败时无法回滚"
  }

  $stage = Join-Path ([System.IO.Path]::GetTempPath()) "int1276-$Name"
  if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
  New-Item -ItemType Directory -Path $stage | Out-Null
  Copy-Item -Recurse $Plan.Dist (Join-Path $stage 'dist')
  Copy-Item $Conf (Join-Path $stage 'nginx-frontend.conf')

  if ($FaultInject -eq 'missing-chunk') {
    $asyncDir = Join-Path $stage 'dist/static/js/async'
    if (Test-Path $asyncDir) {
      $victim = Get-ChildItem $asyncDir -File | Select-Object -First 1
      Remove-Item $victim.FullName -Force
      Write-Warning "[$Name][演练] 已从构建上下文删除 $($victim.Name)，预期自检失败并回滚"
    } else {
      Write-Warning "[$Name][演练] 该 dist 没有 static/js/async，跳过故障注入"
    }
  }

  @'
FROM nginx:alpine
COPY nginx-frontend.conf /etc/nginx/conf.d/default.conf
COPY dist/ /usr/share/nginx/html/
EXPOSE 80
'@ | Set-Content -Path (Join-Path $stage 'Dockerfile') -Encoding utf8

  Write-Host "[$Name] build $image from $($Plan.Dist)（构建时间 $($Plan.BuildTime)）"
  docker build -q -t $image $stage | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "[$Name] docker build 失败" }

  docker rm -f $Name 2>$null | Out-Null
  docker run -d --name $Name --network $Network -p "${Port}:80" $image | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "[$Name] docker run 失败" }

  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/" -TimeoutSec 3
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $ready) {
    Restore-Previous -Name $Name -ImageName $ImageName -Port $Port -RollbackTag $rollbackTag -PrevImageId $prevImageId
    throw "[$Name] 30s 内 :$Port 未就绪，已回滚"
  }

  try {
    Test-Deployed -Name $Name -Port $Port -Plan $Plan
  } catch {
    Write-Warning "[$Name] 自检失败：$($_.Exception.Message)"
    Restore-Previous -Name $Name -ImageName $ImageName -Port $Port -RollbackTag $rollbackTag -PrevImageId $prevImageId
    throw "[$Name] 部署自检失败，已回滚到上一版（$rollbackTag）：$($_.Exception.Message)"
  }

  Write-Host "[$Name] up on :$Port（自检通过）"
}

function Restore-Previous {
  param([string]$Name, [string]$ImageName, [int]$Port, [string]$RollbackTag, [string]$PrevImageId)

  docker rm -f $Name 2>$null | Out-Null
  if (-not $PrevImageId) {
    Write-Warning "[$Name] 没有可回滚的旧镜像，容器已移除"
    return
  }
  $image = "${ImageName}:latest"
  docker tag $RollbackTag $image | Out-Null
  docker run -d --name $Name --network $Network -p "${Port}:80" $image | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Warning "[$Name] 回滚启动失败: $image（tag $RollbackTag 仍可手工恢复）"; return }

  for ($i = 0; $i -lt 30; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/" -TimeoutSec 3
      if ($r.StatusCode -eq 200) { Write-Host "[$Name] 已回滚到 $RollbackTag，:$Port 200"; return }
    } catch { Start-Sleep -Milliseconds 500 }
  }
  Write-Warning "[$Name] 回滚后 30s 内 :$Port 未就绪（旧镜像 $RollbackTag）"
}

# ---- 主流程 ---------------------------------------------------------------
try {
  Acquire-DeployLock

  $plans = @()
  if (-not $SkipReact) { $plans += Test-Dist -Name 'iat-react-frontend' -Dist $ReactDist -Kind 'react' }
  if (-not $SkipVue)   { $plans += Test-Dist -Name 'iat-uxvue-frontend' -Dist $VueDist  -Kind 'vue' }
  if ($plans.Count -eq 0) { throw '两侧都被 -SkipReact / -SkipVue 跳过，无事可做' }

  foreach ($p in $plans) {
    $port = if ($p.Kind -eq 'react') { 15173 } else { 16173 }
    if ($DryRun) {
      Write-Host ("[DRY-RUN] 将部署 {0} -> :{1}（dist={2}，构建时间 {3}，index 引用 chunk {4} 个，async {5}）——只校验不落盘，未执行任何 docker 操作" -f `
          $p.Name, $port, $p.Dist, $p.BuildTime, $p.Chunks.Count, $p.AsyncCount)
      continue
    }
    if ($p.Kind -eq 'react') {
      Deploy-Frontend -Name $p.Name -ImageName 'iat-react-frontend' -Port 15173 -Plan $p
    } else {
      Deploy-Frontend -Name $p.Name -ImageName 'iat-uxvue-frontend' -Port 16173 -Plan $p
    }
  }

  if ($DryRun) { Write-Host '完成（DRY-RUN：两侧校验通过，未部署）。' ; return }
  Write-Host "完成。验收：curl -sI -H 'Accept-Encoding: gzip, br' http://localhost:15173/static/... "
} finally {
  Release-DeployLock
}
