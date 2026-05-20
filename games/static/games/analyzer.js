const analysisComment = document.getElementById('analysis-comment');

//funçao atualiza comentario do coach a cada jogada
function updateAnalysisComment() {
    if (!analysisComment) return;

    if (historyIndex === 0) {
        analysisComment.innerText = 'Posição inicial.';
        return;
    }

    const data = MOVE_ANALYSIS[historyIndex - 1];

    if (!data) {
        analysisComment.innerText = '';
        return;
    }

    analysisComment.innerText = `${data.move_number}. ${data.comment}`;
}

document.getElementById('prev-move').addEventListener('click', updateAnalysisComment);
document.getElementById('next-move').addEventListener('click', updateAnalysisComment);
document.getElementById('last-move').addEventListener('click', updateAnalysisComment);

updateAnalysisComment();
