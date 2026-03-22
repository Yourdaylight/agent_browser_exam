// State
const state = {
    apiUrl: window.location.origin,  // 动态获取，部署无需改代码
    examToken: null,
    currentLevel: 'v1',
    selectedAgent: 'browser-use',
    agentVersion: '1.0.0',
    currentTaskIndex: 0,
    tasks: [],
    results: []
};

// Toast notification
function showToast(message, duration = 2000) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, duration);
}

// Navigate pages
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(`${pageId}-page`);
    if (page) {
        page.classList.add('active');
    }
}

// Load leaderboard
async function loadLeaderboard(level = 'all') {
    const list = document.getElementById('leaderboard-list');
    if (!list) return;

    list.innerHTML = '<div class="leaderboard-empty">加载中...</div>';

    try {
        let entries = [];

        if (level === 'all') {
            // Load all three leaderboards
            const levels = ['v1', 'v2', 'v3'];
            const results = await Promise.all(
                levels.map(l => fetch(`${state.apiUrl}/api/leaderboard/${l}`).then(r => r.json()).catch(() => ({ entries: [] })))
            );
            results.forEach(data => {
                if (data.entries && data.entries.length > 0) {
                    entries = entries.concat(data.entries.map(e => ({ ...e, exam_id: data.level })));
                }
            });
            // Sort by score
            entries.sort((a, b) => b.total_score - a.total_score || a.total_time_seconds - b.total_time_seconds);
            // Re-rank
            entries.forEach((e, i) => e.rank = i + 1);
        } else {
            const response = await fetch(`${state.apiUrl}/api/leaderboard/${level}`);
            const data = await response.json();
            entries = data.entries || [];
        }

        if (entries.length === 0) {
            list.innerHTML = '<div class="leaderboard-empty">暂无数据</div>';
            return;
        }

        list.innerHTML = entries.map(entry => `
            <div class="leaderboard-item">
                <div class="leaderboard-rank ${entry.rank <= 3 ? 'top-3' : ''}">#${entry.rank}</div>
                <div class="leaderboard-info">
                    <h4>${entry.agent_name}</h4>
                    <p>${entry.agent_type} · ${entry.grade}级 · ${entry.exam_id || level}</p>
                </div>
                <div class="leaderboard-score">
                    <div class="score">${entry.total_score}/${entry.max_score}</div>
                    <div class="grade">${entry.total_time_seconds.toFixed(1)}秒</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load leaderboard:', e);
        list.innerHTML = '<div class="leaderboard-empty">加载失败</div>';
    }
}

// Show toast on load
document.addEventListener('DOMContentLoaded', () => {
    // Check API health
    fetch(`${state.apiUrl}/api/health`)
        .then(r => r.json())
        .then(data => {
            console.log('API connected:', data);
        })
        .catch(e => {
            console.warn('API not available:', e);
        });
});
