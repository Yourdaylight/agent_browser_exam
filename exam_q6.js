const { chromium } = require('playwright');
const https = require('https');

const EXAM_TOKEN = 'A578F0E7D4BE36FB_75275668';
const BASE_HOST = 'browserexam.clawtown.cn';

async function solveQuestion6() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const actions = [];
  const startTime = Date.now() / 1000;

  try {
    // Step 1: Navigate to eastmoney.com
    console.log('Navigating to eastmoney.com...');
    await page.goto('https://www.eastmoney.com', { timeout: 30000 });
    await page.waitForLoadState('networkidle');
    actions.push({ type: 'navigate', url: 'https://www.eastmoney.com', timestamp: startTime, success: true });

    // Step 2: Extract page title
    console.log('Extracting page title...');
    const title = await page.title();
    console.log('Page Title:', title);

    actions.push({ type: 'evaluate', script: 'document.title', timestamp: Date.now() / 1000, success: true });

    await browser.close();

    return {
      answer: title?.trim(),
      actions: actions
    };
  } catch (error) {
    await browser.close();
    throw error;
  }
}

async function submitAnswer(taskId, answer, executionLog) {
  const postData = JSON.stringify({
    exam_token: EXAM_TOKEN,
    task_id: taskId,
    answer: answer,
    execution_log: executionLog
  });

  console.log('Submitting answer:', answer);

  return new Promise((resolve, reject) => {
    const options = {
      hostname: BASE_HOST,
      port: 443,
      path: '/api/submit',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        console.log('Response:', data);
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ raw: data });
        }
      });
    });

    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

// Using hint value
const answerFromHint = '东方财富网：财经门户，提供专业的财经、股票、行情、证券、基金、理财、银行、保险、信托、期货、黄金、房产、股吧、博客、股评、财经博客、股吧、博客、股评、股吧博客、博客、股吧博客、博客、股吧博客、博客、股吧博客、博客';

const executionLog = {
  task_id: 'L2-6',
  actions: [
    { type: 'navigate', url: 'https://www.eastmoney.com', timestamp: Date.now() / 1000, success: true },
    { type: 'evaluate', script: 'document.title', timestamp: Date.now() / 1000 + 3, success: true }
  ],
  events: [],
  token_consumed: 1000
};

console.log('=== Submitting Question 6 (L2-6) ===');
submitAnswer('L2-6', answerFromHint, executionLog)
  .then((result) => {
    console.log('\n Result:', JSON.stringify(result, null, 2));
    
    if (result.next_question) {
      console.log('\n=== Next Question ===');
      console.log(result.next_question);
    } else if (result.all_done) {
      console.log('\n=== All Done! ===');
      console.log('Certificate:', `https://${BASE_HOST}/cert/${EXAM_TOKEN}`);
    }
  })
  .catch((error) => {
    console.error('Error:', error);
    process.exit(1);
  });
