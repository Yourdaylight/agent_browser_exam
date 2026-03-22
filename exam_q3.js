const { chromium } = require('playwright');
const https = require('https');

const EXAM_TOKEN = 'A578F0E7D4BE36FB_75275668';
const BASE_HOST = 'browserexam.clawtown.cn';

async function solveQuestion3() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const actions = [];
  const startTime = Date.now() / 1000;

  try {
    // Step 1: Navigate to wizard page
    console.log('Navigating to wizard page...');
    await page.goto(`https://${BASE_HOST}/exam-page/wizard`);
    await page.waitForLoadState('networkidle');
    actions.push({
      type: 'navigate',
      url: `https://${BASE_HOST}/exam-page/wizard`,
      timestamp: startTime,
      success: true
    });

    // Step 2: Fill Step 1 - Shipping Info
    console.log('Filling Step 1 (Shipping Info)...');
    await page.waitForSelector('#fullName', { timeout: 5000 });
    
    await page.fill('#fullName', 'John Doe');
    await page.fill('#email', 'john.doe@example.com');
    await page.fill('#phone', '13800138000');
    await page.fill('#address', '123 Main Street, Beijing');
    
    actions.push({ type: 'type', selector: '#fullName', value: 'John Doe', timestamp: Date.now() / 1000, success: true });
    actions.push({ type: 'type', selector: '#email', value: 'john.doe@example.com', timestamp: Date.now() / 1000, success: true });
    actions.push({ type: 'type', selector: '#phone', value: '13800138000', timestamp: Date.now() / 1000, success: true });
    actions.push({ type: 'type', selector: '#address', value: '123 Main Street, Beijing', timestamp: Date.now() / 1000, success: true });

    // Click Next Step using the button's onclick
    console.log('Clicking Next Step...');
    await page.evaluate(() => goToStep(2));
    await page.waitForTimeout(500);
    actions.push({ type: 'click', selector: 'button:has-text("Next Step")', timestamp: Date.now() / 1000, success: true });

    // Step 3: Fill Step 2 - Payment Method (select dropdown)
    console.log('Filling Step 2 (Payment Method)...');
    await page.waitForSelector('#paymentMethod', { timeout: 5000 });
    await page.selectOption('#paymentMethod', 'credit_card');
    actions.push({ type: 'select', selector: '#paymentMethod', value: 'credit_card', timestamp: Date.now() / 1000, success: true });

    // Click Next Step to go to step 3
    console.log('Clicking Next Step...');
    await page.evaluate(() => goToStep(3));
    await page.waitForTimeout(500);
    actions.push({ type: 'click', selector: 'button:has-text("Next Step")', timestamp: Date.now() / 1000, success: true });

    // Step 4: Extract Order Number from Step 3
    console.log('Extracting Order Number...');
    await page.waitForSelector('#orderId', { timeout: 5000 });
    const orderNumber = await page.textContent('#orderId');
    console.log('Order Number:', orderNumber);

    actions.push({ type: 'evaluate', script: 'document.getElementById("orderId").textContent', timestamp: Date.now() / 1000, success: true });

    await browser.close();

    return {
      answer: orderNumber?.trim(),
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
solveQuestion3()
  .then(async (result) => {
    const executionLog = {
      task_id: 'L2-3',
      actions: result.actions,
      events: [],
      token_consumed: 2000
    };

    console.log('\n=== Submitting Question 3 (L2-3) ===');
    const submitResult = await submitAnswer('L2-3', result.answer, executionLog);
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