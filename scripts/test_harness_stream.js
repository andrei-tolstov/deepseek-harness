const http = require('http');

const data = JSON.stringify({
  model: 'qwen/qwen3.8-max:free',
  messages: [{ role: 'user', content: 'Say hi in two words' }],
  stream: true,
  max_tokens: 15
});

const req = http.request('http://omniroute:20128/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer sk-cb4c532e2e182bc0-083f70-ef5e4ebe',
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data)
  }
}, res => {
  console.log('STATUS:', res.statusCode);
  console.log('HEADERS:', res.headers['content-type']);
  res.on('data', d => {
    process.stdout.write(d.toString());
  });
  res.on('end', () => console.log('\n--- STREAM COMPLETED ---'));
});

req.on('error', e => console.error('REQUEST ERROR:', e));
req.write(data);
req.end();
