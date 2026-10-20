// INT-1068 runtime demo: OpenAI-compatible mock for the 灵犀Agent review conversation.
const http = require('http');
const server = http.createServer((req, res) => {
  if (req.url === '/chat/completions' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        const msgs = Array.isArray(payload.messages) ? payload.messages : [];
        const lastUser = [...msgs].reverse().find(m => m.role === 'user');
        const q = (lastUser && lastUser.content) ? String(lastUser.content).slice(0, 50) : '';
        const reply = '（复核追问回应）关于您的问题「' + q + '」：综合该用例设备×结果与维度得分，低分维度集中在语音一致性（0.85 阈值附近），与 LLM 评语指向一致，建议结论为「复核不通过」，置信度中等，理由：主音内容与参考文本存在可复现偏差，需人工确认后采纳。';
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ choices: [{ message: { role: 'assistant', content: reply } }] }));
      } catch (e) {
        res.writeHead(400); res.end(JSON.stringify({ error: String(e) }));
      }
    });
    return;
  }
  if (req.url === '/models' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ id: 'mock-model' }] }));
    return;
  }
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found' }));
});
server.listen(7799, () => console.log('mock chat listening on 7799'));
