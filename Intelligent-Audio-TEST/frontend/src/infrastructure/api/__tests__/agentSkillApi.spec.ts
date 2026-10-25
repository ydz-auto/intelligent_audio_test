/**
 * agentSkillApi 契约测试（INT-1897 接线：INT-1150 后端 GET /api/v1/agent/skill 已就绪）。
 * 真实请求形态锁定：GET /agent/skill + responseType:'blob' + 查询参数名为 base_url
 * （后端 download_skill(request, base_url: str = '')；写错成 url 则后端落 Origin/Host 兜底）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { downloadSkillPackage } from '../agentSkillApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('downloadSkillPackage 真实请求契约（INT-1897）', () => {
  it('GET /agent/skill，blob 响应，服务地址走 base_url 参数', async () => {
    const zip = new Blob(['zip'], { type: 'application/zip' });
    mockedRequest.mockResolvedValue(zip);

    const result = await downloadSkillPackage({ serviceUrl: 'https://agent.example.com' });

    expect(mockedRequest).toHaveBeenCalledWith('GET', '/agent/skill', null, {
      responseType: 'blob',
      params: { base_url: 'https://agent.example.com' },
    });
    expect(result).toBe(zip);
  });

  it('未传服务地址 → base_url 为 undefined（request 层过滤，后端按 Origin/Host 兜底）', async () => {
    mockedRequest.mockResolvedValue(new Blob(['zip']));

    await downloadSkillPackage();

    expect(mockedRequest).toHaveBeenCalledWith('GET', '/agent/skill', null, {
      responseType: 'blob',
      params: { base_url: undefined },
    });
  });
});
