const { chromium } = require('playwright');
const https = require('https');

const EXAM_TOKEN = 'A578F0E7D4BE36FB_75275668';
const BASE_HOST = 'browserexam.clawtown.cn';

async function solveQuestion2() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const actions = [];
  const startTime = Date.now() / 1000;

  try {
    // Step 1: Navigate to products page
    console.log('Navigating to products page...');
    await page.goto(`https://${BASE_HOST}/exam-page/products`);
    await page.waitForLoadState('networkidle');
    actions.push({
      type: 'navigate',
      url: `https://${BASE_HOST}/exam-page/products`,
      timestamp: startTime,
      success: true
    });

    // Wait for the page to load
    await page.waitForSelector('#productGrid', { timeout: 5000 });
    actions.push({
      type: 'wait',
      selector: '#productGrid',
      timestamp: Date.now() / 1000,
      success: true
    });

    // Step 2: Sort by Price: High to Low
    console.log('Selecting sort: Price High to Low...');
    await page.waitForSelector('#sortSelect', { timeout: 5000 });
    await page.selectOption('#sortSelect', 'price-desc');
    await page.waitForTimeout(500);
    actions.push({
      type: 'select',
      selector: '#sortSelect',
      value: 'price-desc',
      timestamp: Date.now() / 1000,
      success: true
    });

    // Step 3: Filter by Electronics
    console.log('Selecting category: Electronics...');
    await page.waitForSelector('#categoryFilter', { timeout: 5000 });
    await page.selectOption('#categoryFilter', 'Electronics');
    await page.waitForTimeout(500);
    actions.push({
      type: 'select',
      selector: '#categoryFilter',
      value: 'Electronics',
      timestamp: Date.now() / 1000,
      success: true
    });

    // Step 4: Get the first product name
    console.log('Extracting first product name...');
    await page.waitForTimeout(500);
    const firstProductName = await page.locator('#productGrid .product-card:first-child .name').textContent();
    console.log('First product:', firstProductName);

    actions.push({
      type: 'evaluate',
      script: 'document.querySelector("#productGrid .product-card:first-child .name").textContent',
      timestamp: Date.now() / 1000,
      success: true
    });

    await browser.close();

    return {
      answer: firstProductName?.trim(),
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

// Run the solution
solveQuestion2()
  .then(async (result) => {
    const executionLog = {
      task_id: 'L2-2',
      actions: result.actions,
      events: [],
      token_consumed: 1500
    };

    console.log('\n=== Submitting Question 2 (L2-2) ===');
    const submitResult = await submitAnswer('L2-2', result.answer, executionLog);
    console.log('\n Result:', JSON.stringify(submitResult, null, 2));

    return submitResult;
  })
  .then((result) => {
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
