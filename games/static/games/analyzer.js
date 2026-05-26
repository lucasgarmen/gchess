(function () {
const analysisComment = document.getElementById('analysis-comment');
const leaveAnalysisModal = document.getElementById('leave-analysis-modal');
const confirmLeaveAnalysisButton = document.getElementById('confirm-leave-analysis');
const cancelLeaveAnalysisButton = document.getElementById('cancel-leave-analysis');
let pendingAnalysisExit = null;
let analysisExitConfirmed = false;

//funçao atualiza comentario do coach a cada jogada
function updateAnalysisComment() {
    if (!analysisComment) return;

    const currentHistoryIndex = typeof window.gchessHistoryIndex === 'number'
        ? window.gchessHistoryIndex
        : historyIndex;

    if (currentHistoryIndex === 0) {
        analysisComment.innerText = analysisComment.dataset.initialComment || 'Posicao inicial.';
        return;
    }

    const data = MOVE_ANALYSIS[currentHistoryIndex - 1];

    if (!data) {
        analysisComment.innerText = '';
        return;
    }

    analysisComment.innerText = `${data.move_number}. ${data.comment}`;
}

document.addEventListener('gchess:position-changed', updateAnalysisComment);

updateAnalysisComment();

function showLeaveAnalysisModal(nextAction) {
    if (analysisExitConfirmed) {
        nextAction();
        return;
    }

    if (!leaveAnalysisModal) {
        nextAction();
        return;
    }

    pendingAnalysisExit = nextAction;
    leaveAnalysisModal.hidden = false;
    document.body.classList.add('analysis-leave-modal-active');
}

function hideLeaveAnalysisModal() {
    if (leaveAnalysisModal) {
        leaveAnalysisModal.hidden = true;
    }

    pendingAnalysisExit = null;
    document.body.classList.remove('analysis-leave-modal-active');
}

function shouldConfirmAnalysisExitUrl(url) {
    if (!url || url.startsWith('#')) {
        return false;
    }

    let targetUrl;

    try {
        targetUrl = new URL(url, window.location.href);
    } catch (error) {
        return false;
    }

    if (targetUrl.href === window.location.href) {
        return false;
    }

    return true;
}

document.addEventListener('click', function (event) {
    const link = event.target.closest ? event.target.closest('a[href]') : null;

    if (!link) {
        return;
    }

    const href = link.getAttribute('href') || '';

    if (!shouldConfirmAnalysisExitUrl(href)) {
        return;
    }

    if (link.target && link.target !== '_self') {
        return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    showLeaveAnalysisModal(function () {
        window.location.href = link.href;
    });
}, true);

document.addEventListener('submit', function (event) {
    const form = event.target;

    if (!form || form.id === 'trainer-chat-form') {
        return;
    }

    const action = form.getAttribute('action') || window.location.href;

    if (!shouldConfirmAnalysisExitUrl(action) && !form.closest('nav')) {
        return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    showLeaveAnalysisModal(function () {
        form.submit();
    });
}, true);

const languageSelect = document.getElementById('language-select');
if (languageSelect && languageSelect.form) {
    languageSelect.addEventListener('change', function (event) {
        event.preventDefault();
        event.stopImmediatePropagation();
        showLeaveAnalysisModal(function () {
            languageSelect.form.submit();
        });
    }, true);
}

if (confirmLeaveAnalysisButton) {
    confirmLeaveAnalysisButton.addEventListener('click', function () {
        const nextAction = pendingAnalysisExit;
        analysisExitConfirmed = true;
        hideLeaveAnalysisModal();

        if (nextAction) {
            nextAction();
        }
    });
}

if (cancelLeaveAnalysisButton) {
    cancelLeaveAnalysisButton.addEventListener('click', hideLeaveAnalysisModal);
}

if (leaveAnalysisModal) {
    leaveAnalysisModal.addEventListener('click', function (event) {
        if (event.target === leaveAnalysisModal) {
            hideLeaveAnalysisModal();
        }
    });
}

window.addEventListener('beforeunload', function (event) {
    if (analysisExitConfirmed) {
        return;
    }

    event.preventDefault();
    event.returnValue = '';
});
}());
