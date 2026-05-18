let historyIndex = SAVED_MOVES.length;
let lastMove = null;
let currentTurn = 'white';
let selectedSquare = null;
let moveNumber = 1;
let gameOver = false;
let promotionPending = false;
let dragState = null;
let suppressNextClick = false;
let finishedGameSynced = false;
let computerThinking = false;
let coachEnabled = false;
let trainerChatThinking = false;
let boardOrientation = playerColor();
let analysisMode = false;
let analysisBoardState = null;
let analysisGameState = null;
let analysisPositions = [];
let analysisPositionIndex = 0;
let gameClock = typeof GAME_CLOCK !== 'undefined' ? GAME_CLOCK : null;
let drawOffer = typeof DRAW_OFFER !== 'undefined' ? DRAW_OFFER : null;
let timeoutSyncInProgress = false;

const DRAG_PIECE_SCALE = 1.7;

let castlingRights = {
    white: {
        kingMoved: false,
        leftRookMoved: false,
        rightRookMoved: false
    },
    black: {
        kingMoved: false,
        leftRookMoved: false,
        rightRookMoved: false
    }
};

const moveList = document.getElementById('move-list');
const board = document.getElementById('board');
const turnIndicator = document.getElementById('turn-indicator');
const gameStatus = document.getElementById('game-status');
const pgnBox = document.getElementById('pgn-box');
const whiteClock = document.getElementById('white-clock');
const blackClock = document.getElementById('black-clock');
const offerDrawButton = document.getElementById('offer-draw-button');
const resignButton = document.getElementById('resign-button');
const resignConfirmPanel = document.getElementById('resign-confirm-panel');
const confirmResignButton = document.getElementById('confirm-resign-button');
const cancelResignButton = document.getElementById('cancel-resign-button');
const drawOfferPanel = document.getElementById('draw-offer-panel');
const drawOfferText = document.getElementById('draw-offer-text');
const drawOfferActions = document.getElementById('draw-offer-actions');
const acceptDrawButton = document.getElementById('accept-draw-button');
const rejectDrawButton = document.getElementById('reject-draw-button');

const initialPosition = {
    a8: { type: 'rook', color: 'black' },
    b8: { type: 'horse', color: 'black' },
    c8: { type: 'bishop', color: 'black' },
    d8: { type: 'queen', color: 'black' },
    e8: { type: 'king', color: 'black' },
    f8: { type: 'bishop', color: 'black' },
    g8: { type: 'horse', color: 'black' },
    h8: { type: 'rook', color: 'black' },

    a7: { type: 'pawn', color: 'black' },
    b7: { type: 'pawn', color: 'black' },
    c7: { type: 'pawn', color: 'black' },
    d7: { type: 'pawn', color: 'black' },
    e7: { type: 'pawn', color: 'black' },
    f7: { type: 'pawn', color: 'black' },
    g7: { type: 'pawn', color: 'black' },
    h7: { type: 'pawn', color: 'black' },

    a2: { type: 'pawn', color: 'white' },
    b2: { type: 'pawn', color: 'white' },
    c2: { type: 'pawn', color: 'white' },
    d2: { type: 'pawn', color: 'white' },
    e2: { type: 'pawn', color: 'white' },
    f2: { type: 'pawn', color: 'white' },
    g2: { type: 'pawn', color: 'white' },
    h2: { type: 'pawn', color: 'white' },

    a1: { type: 'rook', color: 'white' },
    b1: { type: 'horse', color: 'white' },
    c1: { type: 'bishop', color: 'white' },
    d1: { type: 'queen', color: 'white' },
    e1: { type: 'king', color: 'white' },
    f1: { type: 'bishop', color: 'white' },
    g1: { type: 'horse', color: 'white' },
    h1: { type: 'rook', color: 'white' },
};

const letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];

const pieceFallbacks = {
    queen_white: '♕',
    queen_black: '♛',
};

const pieceFileNames = {
    pawn_white: 'pawn_withe.png',
};

const pieceValues = {
    queen: 9,
    rook: 5,
    bishop: 3,
    horse: 3,
    pawn: 1,
    king: 0,
};

const pieceOrder = ['queen', 'rook', 'bishop', 'horse', 'pawn'];

function squareColor(square) {
    return square.dataset.color || '';
}

function sameColor(square1, square2) {
    return squareColor(square1) !== '' && squareColor(square1) === squareColor(square2);
}

function isKingSquare(square) {
    return square && square.dataset.type === 'king';
}

function isComputerMode() {
    return typeof COMPUTER_MODE !== 'undefined' && COMPUTER_MODE;
}

function playerColor() {
    if (typeof GAME_PLAYER_COLOR !== 'undefined' && GAME_PLAYER_COLOR) {
        return GAME_PLAYER_COLOR;
    }

    return typeof PLAYER_COLOR !== 'undefined' ? PLAYER_COLOR : 'white';
}

function isMultiplayerMode() {
    return typeof MULTIPLAYER_MODE !== 'undefined' && MULTIPLAYER_MODE;
}

function computerColor() {
    return playerColor() === 'white' ? 'black' : 'white';
}

function canPlayerMoveFrom(square) {
    if (analysisMode) {
        return squareColor(square) !== '';
    }

    if (
        !isViewingLatestPosition() ||
        gameOver ||
        computerThinking ||
        squareColor(square) !== currentTurn
    ) {
        return false;
    }

    if (isMultiplayerMode()) {
        return currentTurn === playerColor();
    }

    return !isComputerMode() || currentTurn === playerColor();
}

function updateTurnIndicator() {
    if (analysisMode) {
        turnIndicator.innerText = 'Modo análisis: pruebas temporarias';
        return;
    }

    if (gameOver && isViewingLatestPosition()) {
        turnIndicator.innerText = 'Partida finalizada';
        return;
    }

    if (computerThinking) {
        turnIndicator.innerText = 'Computador pensando...';
        return;
    }

    if (isViewingLatestPosition()) {
        turnIndicator.innerText = currentTurn === 'white'
            ? 'Vez das brancas'
            : 'Vez das pretas';
    } else {
        turnIndicator.innerText = `Vendo jogada ${historyIndex} de ${SAVED_MOVES.length}`;
    }
}

function isViewingLatestPosition() {
    return historyIndex === SAVED_MOVES.length;
}

function boardOrderFor(square) {
    const coord = square.dataset.coord;
    const fileIndex = letters.indexOf(coord[0]);
    const rank = parseInt(coord[1]);

    if (boardOrientation === 'black') {
        return (rank - 1) * 8 + (7 - fileIndex);
    }

    return (8 - rank) * 8 + fileIndex;
}

function updateBoardLabels() {
    const rankLabels = document.querySelectorAll('.rank-labels span');
    const fileLabels = document.querySelectorAll('.file-labels span');
    const ranks = boardOrientation === 'black'
        ? ['1', '2', '3', '4', '5', '6', '7', '8']
        : ['8', '7', '6', '5', '4', '3', '2', '1'];
    const files = boardOrientation === 'black'
        ? [...letters].reverse()
        : letters;

    rankLabels.forEach((label, index) => {
        label.innerText = ranks[index];
    });

    fileLabels.forEach((label, index) => {
        label.innerText = files[index];
    });
}

function updateBoardOrientation() {
    document.querySelectorAll('.square').forEach(square => {
        square.style.order = boardOrderFor(square);
    });
    updateBoardLabels();
}

function flipBoard() {
    boardOrientation = boardOrientation === 'white' ? 'black' : 'white';
    updateBoardOrientation();
}

function snapshotBoardData() {
    return Array.from(document.querySelectorAll('.square')).map(square => ({
        coord: square.dataset.coord,
        color: square.dataset.color,
        type: square.dataset.type,
    }));
}

function restoreBoardData(boardData) {
    boardData.forEach(state => {
        const square = getSquare(state.coord);

        square.replaceChildren();
        square.dataset.color = state.color;
        square.dataset.type = state.type;

        if (state.color && state.type) {
            square.appendChild(createPieceElement({
                color: state.color,
                type: state.type,
            }));
        }
    });
}

function recordAnalysisPosition() {
    analysisPositions = analysisPositions.slice(0, analysisPositionIndex + 1);
    analysisPositions.push(snapshotBoardData());
    analysisPositionIndex = analysisPositions.length - 1;
    updateHistoryControls();
}

function showAnalysisPosition(nextIndex) {
    if (!analysisMode || nextIndex < 0 || nextIndex >= analysisPositions.length) {
        return;
    }

    clearSelection();
    analysisPositionIndex = nextIndex;
    restoreBoardData(analysisPositions[analysisPositionIndex]);
    updateCapturedMaterial();
    updateHistoryControls();
}

function showPreviousAnalysisPosition() {
    showAnalysisPosition(analysisPositionIndex - 1);
}

function showNextAnalysisPosition() {
    showAnalysisPosition(analysisPositionIndex + 1);
}

function enterAnalysisMode() {
    if (computerThinking || promotionPending) {
        return;
    }

    clearSelection();
    analysisBoardState = snapshotBoard();
    analysisGameState = {
        currentTurn: currentTurn,
        lastMove: lastMove,
        gameOver: gameOver,
        moveNumber: moveNumber,
        historyIndex: historyIndex,
        castlingRights: JSON.parse(JSON.stringify(castlingRights)),
    };
    analysisPositions = [snapshotBoardData()];
    analysisPositionIndex = 0;
    analysisMode = true;
    board.classList.add('analysis-board');
    hideGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function exitAnalysisMode() {
    if (!analysisMode) {
        return;
    }

    clearSelection();
    restoreBoard(analysisBoardState);
    currentTurn = analysisGameState.currentTurn;
    lastMove = analysisGameState.lastMove;
    gameOver = analysisGameState.gameOver;
    moveNumber = analysisGameState.moveNumber;
    historyIndex = analysisGameState.historyIndex;
    castlingRights = analysisGameState.castlingRights;
    analysisMode = false;
    analysisBoardState = null;
    analysisGameState = null;
    analysisPositions = [];
    analysisPositionIndex = 0;
    board.classList.remove('analysis-board');
    refreshGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function toggleAnalysisMode() {
    if (analysisMode) {
        exitAnalysisMode();
    } else {
        enterAnalysisMode();
    }
}

function resetCastlingRights() {
    castlingRights = {
        white: {
            kingMoved: false,
            leftRookMoved: false,
            rightRookMoved: false
        },
        black: {
            kingMoved: false,
            leftRookMoved: false,
            rightRookMoved: false
        }
    };
}

function updateCastlingRightsAfterMove(move) {
    const movingType = move.piece_type;
    const movingColor = move.piece_color;
    const from = move.from;

    if (movingType === 'king') {
        castlingRights[movingColor].kingMoved = true;
    }

    if (movingType === 'rook') {
        if (from === 'a1') castlingRights.white.leftRookMoved = true;
        if (from === 'h1') castlingRights.white.rightRookMoved = true;
        if (from === 'a8') castlingRights.black.leftRookMoved = true;
        if (from === 'h8') castlingRights.black.rightRookMoved = true;
    }
}

function updateHistoryControls() {
    document.getElementById('prev-move').disabled = analysisMode || historyIndex === 0;
    document.getElementById('next-move').disabled = analysisMode || historyIndex === SAVED_MOVES.length;
    document.getElementById('last-move').disabled = analysisMode || isViewingLatestPosition();

    const undoComputerButton = document.getElementById('undo-computer-move');
    if (undoComputerButton) {
        undoComputerButton.disabled = analysisMode || computerThinking || SAVED_MOVES.length === 0;
    }

    const resetComputerButton = document.getElementById('reset-computer-game');
    if (resetComputerButton) {
        resetComputerButton.disabled = analysisMode || computerThinking || SAVED_MOVES.length === 0;
    }

    const toggleCoachButton = document.getElementById('toggle-coach');
    if (toggleCoachButton) {
        toggleCoachButton.innerText = coachEnabled ? 'Desabilitar treinador' : 'Habilitar treinador';
    }

    const playerColorSelect = document.getElementById('player-color');
    if (playerColorSelect) {
        playerColorSelect.disabled = analysisMode || computerThinking || SAVED_MOVES.length > 0;
    }

    const analysisModeButton = document.getElementById('toggle-analysis-mode');
    if (analysisModeButton) {
        analysisModeButton.innerText = analysisMode ? 'Salir análisis' : 'Modo análisis';
        analysisModeButton.classList.toggle('active', analysisMode);
    }

    const analysisPrevButton = document.getElementById('analysis-prev');
    if (analysisPrevButton) {
        analysisPrevButton.hidden = !analysisMode;
        analysisPrevButton.disabled = analysisPositionIndex === 0;
    }

    const analysisNextButton = document.getElementById('analysis-next');
    if (analysisNextButton) {
        analysisNextButton.hidden = !analysisMode;
        analysisNextButton.disabled = analysisPositionIndex >= analysisPositions.length - 1;
    }
}

function showGameStatus(message) {
    gameStatus.innerText = message;
    gameStatus.hidden = false;
}

function hideGameStatus() {
    gameStatus.hidden = true;
    gameStatus.innerText = '';
}

function initialPieceCounts() {
    const counts = {
        white: {},
        black: {},
    };

    Object.values(initialPosition).forEach(piece => {
        counts[piece.color][piece.type] = (counts[piece.color][piece.type] || 0) + 1;
    });

    return counts;
}

function currentPieceCounts() {
    const counts = {
        white: {},
        black: {},
    };

    document.querySelectorAll('.square').forEach(square => {
        const color = square.dataset.color;
        const type = square.dataset.type;

        if (!color || !type || type === 'king') {
            return;
        }

        counts[color][type] = (counts[color][type] || 0) + 1;
    });

    return counts;
}

function capturedPiecesFor(color) {
    const initialCounts = initialPieceCounts();
    const currentCounts = currentPieceCounts();
    const captured = [];

    pieceOrder.forEach(type => {
        const missing = (initialCounts[color][type] || 0) - (currentCounts[color][type] || 0);

        for (let i = 0; i < missing; i++) {
            captured.push({ type: type, color: color });
        }
    });

    return captured;
}

function materialValue(pieces) {
    return pieces.reduce((total, piece) => total + (pieceValues[piece.type] || 0), 0);
}

function renderCapturedPieces(containerId, pieces) {
    const container = document.getElementById(containerId);

    if (!container) {
        return;
    }

    container.replaceChildren();

    pieces.forEach(piece => {
        const pieceElement = createPieceElement(piece);
        pieceElement.classList.add('captured-piece');
        container.appendChild(pieceElement);
    });
}

function updateCapturedMaterial() {
    const capturedBlack = capturedPiecesFor('black');
    const capturedWhite = capturedPiecesFor('white');
    const whiteCapturedValue = materialValue(capturedBlack);
    const blackCapturedValue = materialValue(capturedWhite);
    const advantage = whiteCapturedValue - blackCapturedValue;
    const whiteAdvantage = document.getElementById('white-material-advantage');
    const blackAdvantage = document.getElementById('black-material-advantage');

    renderCapturedPieces('captured-black', capturedBlack);
    renderCapturedPieces('captured-white', capturedWhite);

    if (whiteAdvantage) {
        whiteAdvantage.innerText = advantage > 0 ? `+${advantage}` : '';
    }

    if (blackAdvantage) {
        blackAdvantage.innerText = advantage < 0 ? `+${Math.abs(advantage)}` : '';
    }
}

function selectSquare(square) {
    selectedSquare = square;
    square.classList.add('selected');

    const moves = getLegalMoves(square);
    highlightMoves(moves);
}

function clearSelection() {
    if (selectedSquare !== null) {
        selectedSquare.classList.remove('selected');
    }

    document.querySelectorAll('.possible-move').forEach(square => {
        square.classList.remove('possible-move');
    });

    selectedSquare = null;
}

function switchTurn() {
    currentTurn = currentTurn === 'white' ? 'black' : 'white';
    updateTurnIndicator();
}


function movePiece(fromSquare, toSquare) {
    toSquare.replaceChildren(...fromSquare.childNodes);
    toSquare.dataset.color = fromSquare.dataset.color;
    toSquare.dataset.type = fromSquare.dataset.type;

    fromSquare.replaceChildren();
    fromSquare.dataset.color = '';
    fromSquare.dataset.type = '';
}

async function playAnalysisMove(fromSquare, toSquare, shouldAnimate = true) {
    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;
    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;

    if (shouldAnimate) {
        await animateMove(fromSquare, toSquare);
    }

    if (
        movingType === 'pawn' &&
        from[0] !== to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnSquare = getSquare(to[0] + from[1]);

        if (capturedPawnSquare) {
            capturedPawnSquare.replaceChildren();
            capturedPawnSquare.dataset.color = '';
            capturedPawnSquare.dataset.type = '';
        }
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);

    if (isPromotionMove(movingType, movingColor, to)) {
        const promotedType = await choosePromotionPiece(toSquare, movingColor);
        promotePawn(toSquare, movingColor, promotedType);
    }

    clearSelection();
    recordAnalysisPosition();
    updateCapturedMaterial();
}

function isPromotionMove(pieceType, pieceColor, toCoord) {
    if (pieceType !== 'pawn') {
        return false;
    }

    const promotionRow = pieceColor === 'white' ? 8 : 1;

    return getRow(toCoord) === promotionRow;
}

function promotePawn(square, color, promotedType) {
    square.dataset.type = promotedType;
    square.replaceChildren(
        createPieceElement({
            type: promotedType,
            color: color
        })
    );
}

function getSquareFromPoint(x, y) {
    const element = document.elementFromPoint(x, y);

    return element ? element.closest('.square') : null;
}

function createDragPiece(square, event) {
    const piece = square.firstElementChild;

    if (!piece) {
        return null;
    }

    const squareRect = square.getBoundingClientRect();
    const dragPiece = piece.cloneNode(true);

    dragPiece.classList.add('drag-piece');
    dragPiece.style.left = '0';
    dragPiece.style.top = '0';
    dragPiece.style.width = `${squareRect.width * DRAG_PIECE_SCALE}px`;
    dragPiece.style.height = `${squareRect.height * DRAG_PIECE_SCALE}px`;
    dragPiece.draggable = false;

    document.body.appendChild(dragPiece);
    square.classList.add('drag-origin');

    moveDragPiece(dragPiece, event);

    return dragPiece;
}

function moveDragPiece(dragPiece, event) {
    dragPiece.style.transform = `translate(${event.clientX - dragPiece.offsetWidth / 2}px, ${event.clientY - dragPiece.offsetHeight / 2}px)`;
}

function cleanupDragState() {
    if (!dragState) {
        return;
    }

    document.removeEventListener('pointermove', handlePieceDrag);
    document.removeEventListener('pointerup', finishPieceDrag);
    document.removeEventListener('pointercancel', cancelPieceDrag);
    window.removeEventListener('blur', cancelPieceDrag);

    if (dragState.pointerId !== null && dragState.originSquare.hasPointerCapture?.(dragState.pointerId)) {
        dragState.originSquare.releasePointerCapture(dragState.pointerId);
    }

    dragState.originSquare.classList.remove('drag-origin');
    dragState.dragPiece.remove();
    dragState = null;
}

function animateMove(fromSquare, toSquare) {
    const piece = fromSquare.firstElementChild;

    if (!piece || !piece.animate) {
        return Promise.resolve();
    }

    const fromRect = fromSquare.getBoundingClientRect();
    const toRect = toSquare.getBoundingClientRect();
    const pieceRect = piece.getBoundingClientRect();
    const movingPiece = piece.cloneNode(true);

    movingPiece.classList.add('move-animation-piece');
    movingPiece.style.left = `${pieceRect.left}px`;
    movingPiece.style.top = `${pieceRect.top}px`;
    movingPiece.style.width = `${pieceRect.width}px`;
    movingPiece.style.height = `${pieceRect.height}px`;

    document.body.appendChild(movingPiece);
    fromSquare.classList.add('drag-origin');

    return movingPiece.animate(
        [
            { transform: 'translate(0, 0)' },
            { transform: `translate(${toRect.left - fromRect.left}px, ${toRect.top - fromRect.top}px)` }
        ],
        {
            duration: 180,
            easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)'
        }
    ).finished.finally(() => {
        fromSquare.classList.remove('drag-origin');
        movingPiece.remove();
    });
}

async function playMove(fromSquare, toSquare, shouldAnimate = true, forcedPromotion = null) {
    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;

    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;

    if (shouldAnimate) {
        await animateMove(fromSquare, toSquare);
    }

    // comer al paso
    if (
        movingType === 'pawn' &&
        from[0] !== to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnCoord = to[0] + from[1];
        const capturedPawnSquare = document.querySelector(`[data-coord="${capturedPawnCoord}"]`);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    // enroque
    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);

    let promotedType = null;

    // promoção de peão
    if (isPromotionMove(movingType, movingColor, to)) {
        promotedType = forcedPromotion || await choosePromotionPiece(toSquare, movingColor);
        promotePawn(toSquare, movingColor, promotedType);
    }

    const playedMove = {
        move_number: moveNumber,
        from: from,
        to: to,
        piece_type: movingType,
        piece_color: movingColor,
        promotion: promotedType || null
    };

    if (isComputerMode()) {
        const eloSelect = document.getElementById('computer-elo');
        if (eloSelect) {
            eloSelect.disabled = true;
        }
    }

    updateCastlingRightsAfterMove(playedMove);
    lastMove = playedMove;

    SAVED_MOVES.push(playedMove);
    historyIndex = SAVED_MOVES.length;
    moveNumber = SAVED_MOVES.length + 1;

    clearSelection();
    switchTurn();

    const gameOutcome = checkGameEnd();
    const gameEnded = Boolean(gameOutcome);

    renderSavedMoveList();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();

    saveMoveToDatabase(playedMove, {
        finished: gameEnded,
        winner: gameOutcome?.winner || null,
        result: gameOutcome?.result || null,
    });

    if (isComputerMode() && coachEnabled && movingColor === playerColor()) {
        requestCoachAnalysis();
    }

    if (
        isComputerMode() &&
        !gameEnded &&
        currentTurn === computerColor()
    ) {
        await askComputerMove();
    }
}

function startPieceDrag(square, event) {
    if (promotionPending) {
        return;
    }

    if (
        selectedSquare !== null &&
        selectedSquare !== square &&
        !sameColor(selectedSquare, square) &&
        isPossibleMove(square)
    ) {
        return;
    }

    event.preventDefault();

    cleanupDragState();

    const dragPiece = createDragPiece(square, event);

    if (!dragPiece) {
        return;
    }

    clearSelection();
    suppressNextClick = true;

    const canPlayFromSquare = canPlayerMoveFrom(square);

    if (canPlayFromSquare) {
        selectSquare(square);
    }

    dragState = {
        originSquare: square,
        dragPiece: dragPiece,
        pointerId: event.pointerId ?? null,
        canPlayFromSquare: canPlayFromSquare
    };

    if (event.pointerId !== undefined && square.setPointerCapture) {
        square.setPointerCapture(event.pointerId);
    }

    document.addEventListener('pointermove', handlePieceDrag);
    document.addEventListener('pointerup', finishPieceDrag);
    document.addEventListener('pointercancel', cancelPieceDrag);
    window.addEventListener('blur', cancelPieceDrag);
}

function handlePieceDrag(event) {
    if (!dragState) {
        return;
    }

    if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) {
        return;
    }

    event.preventDefault();
    moveDragPiece(dragState.dragPiece, event);
}

async function finishPieceDrag(event) {
    if (!dragState) {
        return;
    }

    if (dragState.pointerId !== null && event.pointerId !== dragState.pointerId) {
        return;
    }

    event.preventDefault();

    const originSquare = dragState.originSquare;
    const targetSquare = getSquareFromPoint(event.clientX, event.clientY);
    const canPlayFromSquare = dragState.canPlayFromSquare;

    cleanupDragState();

    if (!canPlayFromSquare) {
        clearSelection();
        return;
    }

    if (targetSquare === originSquare) {
        return;
    }

    if (!targetSquare || !isPossibleMove(targetSquare)) {
        clearSelection();
        return;
    }

    if (analysisMode) {
        await playAnalysisMove(originSquare, targetSquare, false);
    } else {
        await playMove(originSquare, targetSquare, false);
    }
}

function cancelPieceDrag() {
    cleanupDragState();
    clearSelection();
}

function createPieceElement(position) {
    const pieceKey = `${position.type}_${position.color}`;
    const pieceImage = document.createElement('img');
    const fileName = pieceFileNames[pieceKey] || `${pieceKey}.png`;

    pieceImage.src = `/static/games/pieces/${fileName}`;
    pieceImage.alt = pieceKey;
    pieceImage.draggable = false;
    pieceImage.classList.add('piece');

    pieceImage.onerror = function () {
        const fallback = document.createElement('span');
        fallback.classList.add('piece-fallback');
        fallback.innerText = pieceFallbacks[pieceKey] || '?';

        pieceImage.replaceWith(fallback);
    };

    return pieceImage;
}

updateTurnIndicator();

for (let row = 8; row >= 1; row--) {
    for (let col = 0; col < 8; col++) {
        const square = document.createElement('div');
        const coord = letters[col] + row;

        square.classList.add('square');
        square.dataset.coord = coord;

        const isLight = (row + col) % 2 === 0;
        square.classList.add(isLight ? 'square-light' : 'square-dark');

        const position = initialPosition[coord];

        square.style.backgroundColor = isLight ? '#f0d9b5' : '#b58863';
       
        if (position) {
            square.appendChild(createPieceElement(position));
            square.dataset.color = position.color;
            square.dataset.type = position.type;
        } else {
            square.dataset.color = '';
            square.dataset.type = '';
        }

        square.addEventListener('pointerdown', function (event) {
            if (event.button !== 0) {
                return;
            }

            startPieceDrag(square, event);
        });

        square.addEventListener('click', async function () {
            if (suppressNextClick) {
                suppressNextClick = false;
                return;
            }

            if (promotionPending) {
                return;
            }

            if (!isViewingLatestPosition() || gameOver) {
                if (!analysisMode) {
                    clearSelection();
                    return;
                }
            }

            if (selectedSquare === null) {
                if (canPlayerMoveFrom(square)) {
                    selectSquare(square);
                }

                return;
            }

            if (selectedSquare === square) {
                clearSelection();
                return;
            }

            if (sameColor(selectedSquare, square)) {
                clearSelection();

                if (canPlayerMoveFrom(square)) {
                    selectSquare(square);
                }

                return;
            }
            

            if (!isPossibleMove(square)) {
                return;
            }

            if (analysisMode) {
                await playAnalysisMove(selectedSquare, square);
            } else {
                await playMove(selectedSquare, square);
            }
        });

        board.appendChild(square);
    }
}

updateBoardOrientation();
renderSavedMoveList();
loadPositionUntil(SAVED_MOVES.length);
updateCapturedMaterial();
renderClock();
renderDrawOffer();

if (clockIsEnabled()) {
    setInterval(renderClock, 1000);
}

if (isMultiplayerMode()) {
    setInterval(syncMovesFromServer, 1500);
}

function clockIsEnabled() {
    return Boolean(gameClock && gameClock.enabled);
}

function secondsSinceClockStart() {
    if (!clockIsEnabled() || !gameClock.started_at || !gameClock.server_now) {
        return 0;
    }

    const serverStartedAt = new Date(gameClock.started_at).getTime();
    const serverNow = new Date(gameClock.server_now).getTime();
    const localNow = Date.now();

    if (Number.isNaN(serverStartedAt) || Number.isNaN(serverNow)) {
        return 0;
    }

    return Math.max(0, Math.floor((localNow - serverNow + serverNow - serverStartedAt) / 1000));
}

function liveClockSeconds(color) {
    if (!clockIsEnabled()) {
        return null;
    }

    const baseSeconds = color === 'white'
        ? gameClock.white_seconds
        : gameClock.black_seconds;

    if (gameOver || gameClock.status === 'finished' || gameClock.active_color !== color) {
        return Math.max(0, baseSeconds || 0);
    }

    return Math.max(0, (baseSeconds || 0) - secondsSinceClockStart());
}

function formatClock(seconds) {
    seconds = Math.max(0, Math.ceil(seconds || 0));

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

function applyClockState(clock) {
    if (!clock) {
        return;
    }

    gameClock = clock;

    if (clock.status === 'finished') {
        gameOver = true;
        finishedGameSynced = true;

        if (clock.result === 'white' || clock.result === 'black') {
            showGameStatus(clock.result === 'white' ? 'Vitória das brancas' : 'Vitória das pretas');
        } else if (clock.result === 'draw') {
            showGameStatus('Partida empatada');
        }
    }

    renderClock();
}

function showServerGameResult(data) {
    if (!data || !data.game_finished) {
        return;
    }

    gameOver = true;
    renderDrawOffer();
    hideResignConfirmPanel();

    if (offerDrawButton) {
        offerDrawButton.disabled = true;
    }

    if (resignButton) {
        resignButton.disabled = true;
    }

    if (data.result === 'draw') {
        showGameStatus('Partida empatada');
        updateTurnIndicator();
        return;
    }

    if (data.winner === 'white' || data.winner === 'black') {
        showGameStatus(data.winner === 'white' ? 'Vitória das brancas' : 'Vitória das pretas');
        updateTurnIndicator();
    }
}

function applyDrawOfferState(offer) {
    if (!offer) {
        return;
    }

    drawOffer = offer;
    renderDrawOffer();
}

function renderDrawOffer() {
    if (!drawOfferPanel || !drawOfferText) {
        return;
    }

    if (offerDrawButton) {
        offerDrawButton.disabled = gameOver || Boolean(drawOffer && drawOffer.pending && !drawOffer.can_accept);
    }

    if (resignButton) {
        resignButton.disabled = gameOver;
    }

    if (!drawOffer || !drawOffer.pending || gameOver) {
        drawOfferPanel.hidden = true;
        return;
    }

    drawOfferPanel.hidden = false;

    if (drawOffer.can_accept) {
        drawOfferText.innerText = 'Seu oponente ofereceu empate.';
        if (drawOfferActions) {
            drawOfferActions.hidden = false;
        }
    } else {
        drawOfferText.innerText = 'Oferta de empate enviada. Aguardando resposta.';
        if (drawOfferActions) {
            drawOfferActions.hidden = true;
        }
    }
}

function showResignConfirmPanel() {
    if (!resignConfirmPanel || gameOver) {
        return;
    }

    resignConfirmPanel.hidden = false;
}

function hideResignConfirmPanel() {
    if (resignConfirmPanel) {
        resignConfirmPanel.hidden = true;
    }
}

async function postGameAction(url, payload = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || 'A ação não pôde ser concluída.');
    }

    applyClockState(data.clock);
    applyDrawOfferState(data.draw_offer);
    showServerGameResult(data);

    return data;
}

function renderClock() {
    if (!clockIsEnabled() || !whiteClock || !blackClock) {
        return;
    }

    const whiteSeconds = liveClockSeconds('white');
    const blackSeconds = liveClockSeconds('black');

    whiteClock.innerText = formatClock(whiteSeconds);
    blackClock.innerText = formatClock(blackSeconds);

    document.querySelectorAll('.clock-row').forEach(row => {
        const color = row.dataset.clockColor;
        const seconds = color === 'white' ? whiteSeconds : blackSeconds;
        row.classList.toggle('active', !gameOver && gameClock.active_color === color);
        row.classList.toggle('flagged', seconds <= 0);
    });

    if (!gameOver && gameClock.status !== 'finished') {
        if (whiteSeconds <= 0) {
            finishByTimeout('white');
        } else if (blackSeconds <= 0) {
            finishByTimeout('black');
        }
    }
}

function finishByTimeout(loser) {
    if (timeoutSyncInProgress || gameOver) {
        return;
    }

    const winner = loser === 'white' ? 'black' : 'white';
    timeoutSyncInProgress = true;
    gameOver = true;
    clearSelection();
    showGameStatus(loser === 'white' ? 'Tempo das brancas esgotado' : 'Tempo das pretas esgotado');
    updateTurnIndicator();

    syncFinishedGame(winner, {
        reason: 'timeout',
        loser: loser,
    });
}

function coordToPosition(coord) {
    const file = coord[0];
    const rank = parseInt(coord[1]);

    return {
        col: letters.indexOf(file),
        row: rank
    };
}

function positionToCoord(col, row) {
    if (col < 0 || col > 7 || row < 1 || row > 8) {
        return null;
    }

    return letters[col] + row;
}

function getHorseMoves(square) {
    const { col, row } = coordToPosition(square.dataset.coord);

    const moves = [
        [1, 2], [2, 1],
        [2, -1], [1, -2],
        [-1, -2], [-2, -1],
        [-2, 1], [-1, 2],
    ];

    return moves
        .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
        .filter(coord => coord !== null);
}


function getPawnMoves(square) {
    const moves = [];

    const { col, row } = coordToPosition(square.dataset.coord);
    const color = square.dataset.color;

    const direction = color === 'white' ? 1 : -1;
    const startRow = color === 'white' ? 2 : 7;
    const enPassantRow = color === 'white' ? 5 : 4;

    // 1 casa para frente
    const frontCoord = positionToCoord(col, row + direction);

    if (frontCoord) {
        const frontSquare = document.querySelector(`[data-coord="${frontCoord}"]`);

        if (frontSquare.dataset.color === '') {
            moves.push(frontCoord);

            // 2 casas para frente desde a posição inicial
            const doubleFrontCoord = positionToCoord(col, row + direction * 2);

            if (row === startRow && doubleFrontCoord) {
                const doubleFrontSquare = document.querySelector(`[data-coord="${doubleFrontCoord}"]`);

                if (doubleFrontSquare.dataset.color === '') {
                    moves.push(doubleFrontCoord);
                }
            }
        }
    }

    // capturas diagonales normales
    const captureCoords = [
        positionToCoord(col - 1, row + direction),
        positionToCoord(col + 1, row + direction),
    ];

    captureCoords.forEach(coord => {
        if (!coord) return;

        const targetSquare = document.querySelector(`[data-coord="${coord}"]`);

        if (
            targetSquare.dataset.color !== '' &&
            targetSquare.dataset.color !== color
        ) {
            moves.push(coord);
        }
    });

    // comer al paso
    if (row === enPassantRow && lastMove !== null) {
        const lastFrom = coordToPosition(lastMove.from);
        const lastTo = coordToPosition(lastMove.to);

        const enemyPawnMovedTwo =
            lastMove.piece_type === 'pawn' &&
            lastMove.piece_color !== color &&
            Math.abs(lastTo.row - lastFrom.row) === 2;

        const enemyPawnIsBeside =
            lastTo.row === row &&
            Math.abs(lastTo.col - col) === 1;

        if (enemyPawnMovedTwo && enemyPawnIsBeside) {
            const enPassantCoord = positionToCoord(lastTo.col, row + direction);
            moves.push(enPassantCoord);
        }
    }

    return moves;
}


function highlightMoves(coords) {
    coords.forEach(coord => {
        const square = document.querySelector(`[data-coord="${coord}"]`);

        if (square && !sameColor(selectedSquare, square) && !isKingSquare(square)) {
            square.classList.add('possible-move');
        }
    });
}

function isPossibleMove(square) {
    return square.classList.contains('possible-move');
}

function getRow(coord) {
    return Number(coord[1]);
}

function getCol(coord) {
    return letters.indexOf(coord[0]);
}

function isValidPawnMove(piece, from, to, targetPiece) {
    const fromRow = getRow(from);
    const toRow = getRow(to);
    const fromCol = getCol(from);
    const toCol = getCol(to);

    const direction = isWhitePiece(piece) ? 1 : -1;
    const startRow = isWhitePiece(piece) ? 2 : 7;

    const rowDiff = toRow - fromRow;
    const colDiff = Math.abs(toCol - fromCol);

    // mover 1 casa para frente
    if (fromCol === toCol && targetPiece === '') {
        if (rowDiff === direction) {
            return true;
        }

        // mover 2 casas desde a posição inicial
        if (fromRow === startRow && rowDiff === direction * 2) {
            return true;
        }
    }

    // capturar diagonal
    if (colDiff === 1 && targetPiece !== '') {
        return rowDiff === direction;
    }

    return false;
}

function isValidRookMove(from, to) {
    const fromRow = getRow(from);
    const toRow = getRow(to);
    const fromCol = getCol(from);
    const toCol = getCol(to);

    return fromRow === toRow || fromCol === toCol;
}

function getPossibleMoves(square) {
    const type = square.dataset.type;

    if (type === 'horse') {
        return getHorseMoves(square);
    }

    if (type === 'pawn') {
        return getPawnMoves(square);
    }

    if (type === 'rook') {
        return getRookMoves(square);
    }

    if (type === 'bishop') {
        return getBishopMoves(square);
    }

    if (type === 'queen') {
        return getQueenMoves(square);
    }

    if (type === 'king') {
        return getKingMoves(square);
    }

    return [];
}

function getLegalMoves(square) {
    if (analysisMode) {
        return getPossibleMoves(square).filter(coord => {
            const targetSquare = getSquare(coord);
            return targetSquare && !sameColor(square, targetSquare) && !isKingSquare(targetSquare);
        });
    }

    return getPossibleMoves(square).filter(coord => isLegalMove(square, getSquare(coord)));
}

function isLegalMove(fromSquare, toSquare) {
    if (!toSquare || sameColor(fromSquare, toSquare) || isKingSquare(toSquare)) {
        return false;
    }

    const movingColor = fromSquare.dataset.color;
    const boardState = snapshotBoard();

    applyMoveForValidation(fromSquare, toSquare);

    const kingCoord = findKingCoord(movingColor);
    const isLegal = kingCoord !== null && !isSquareAttacked(kingCoord, getEnemyColor(movingColor));

    restoreBoard(boardState);

    return isLegal;
}

function snapshotBoard() {
    return Array.from(document.querySelectorAll('.square')).map(square => ({
        square: square,
        color: square.dataset.color,
        type: square.dataset.type,
        children: Array.from(square.childNodes),
    }));
}

function restoreBoard(boardState) {
    boardState.forEach(state => {
        state.square.replaceChildren(...state.children);
        state.square.dataset.color = state.color;
        state.square.dataset.type = state.type;
    });
}

function applyMoveForValidation(fromSquare, toSquare) {
    const movingType = fromSquare.dataset.type;
    const movingColor = fromSquare.dataset.color;
    const from = fromSquare.dataset.coord;
    const to = toSquare.dataset.coord;

    if (
        movingType === 'pawn' &&
        from[0] !== to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnSquare = getSquare(to[0] + from[1]);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(from) - getCol(to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
}

function findKingCoord(color) {
    const kingSquare = Array.from(document.querySelectorAll('.square')).find(square => {
        return square.dataset.type === 'king' && square.dataset.color === color;
    });

    return kingSquare ? kingSquare.dataset.coord : null;
}

function isKingInCheck(color) {
    const kingCoord = findKingCoord(color);

    return kingCoord !== null && isSquareAttacked(kingCoord, getEnemyColor(color));
}

function hasAnyLegalMove(color) {
    const pieces = Array.from(document.querySelectorAll('.square')).filter(square => {
        return square.dataset.color === color;
    });

    return pieces.some(square => getLegalMoves(square).length > 0);
}

function isCheckmate(color) {
    return isKingInCheck(color) && !hasAnyLegalMove(color);
}

function isStalemate(color) {
    return !isKingInCheck(color) && !hasAnyLegalMove(color);
}

function bishopSquareColor(coord) {
    return (getCol(coord) + getRow(coord)) % 2;
}

function currentNonKingPieces() {
    return Array.from(document.querySelectorAll('.square'))
        .filter(square => square.dataset.color && square.dataset.type && square.dataset.type !== 'king')
        .map(square => ({
            type: square.dataset.type,
            color: square.dataset.color,
            coord: square.dataset.coord,
        }));
}

function hasInsufficientMaterial() {
    const pieces = currentNonKingPieces();

    if (pieces.length === 0) {
        return true;
    }

    if (pieces.length === 1 && ['bishop', 'horse'].includes(pieces[0].type)) {
        return true;
    }

    if (pieces.length === 2 && pieces.every(piece => piece.type === 'bishop')) {
        return bishopSquareColor(pieces[0].coord) === bishopSquareColor(pieces[1].coord);
    }

    return false;
}

function checkGameEnd() {
    if (analysisMode) {
        return null;
    }

    if (isCheckmate(currentTurn)) {
        gameOver = true;
        clearSelection();
        showGameStatus('xeque-mate!');
        updateTurnIndicator();
        return {
            result: getEnemyColor(currentTurn),
            winner: getEnemyColor(currentTurn),
        };
    }

    if (isStalemate(currentTurn)) {
        gameOver = true;
        clearSelection();
        showGameStatus('Partida empatada por ahogado');
        updateTurnIndicator();
        return {
            result: 'draw',
            winner: null,
        };
    }

    if (hasInsufficientMaterial()) {
        gameOver = true;
        clearSelection();
        showGameStatus('Partida empatada por material insuficiente');
        updateTurnIndicator();
        return {
            result: 'draw',
            winner: null,
        };
    }

    return null;
}

function refreshGameStatus() {
    if (analysisMode) {
        hideGameStatus();
        return;
    }

    gameOver = isViewingLatestPosition() && (isCheckmate(currentTurn) || isStalemate(currentTurn) || hasInsufficientMaterial());

    if (gameOver && isCheckmate(currentTurn)) {
        showGameStatus('xeque-mate!');
        syncFinishedGame(getEnemyColor(currentTurn));
    } else if (gameOver && isStalemate(currentTurn)) {
        showGameStatus('Partida empatada por ahogado');
        syncFinishedGame(null, { result: 'draw' });
    } else if (gameOver && hasInsufficientMaterial()) {
        showGameStatus('Partida empatada por material insuficiente');
        syncFinishedGame(null, { result: 'draw' });
    } else {
        hideGameStatus();
    }
}

function getSlidingMoves(square, directions) {
    const moves = [];
    const { col, row } = coordToPosition(square.dataset.coord);

    directions.forEach(([dc, dr]) => {
        let nextCol = col + dc;
        let nextRow = row + dr;

        while (true) {
            const coord = positionToCoord(nextCol, nextRow);

            if (coord === null) {
                break;
            }

            const targetSquare = document.querySelector(`[data-coord="${coord}"]`);

            if (targetSquare.dataset.color === '') {
                moves.push(coord);
            } else {
                if (!sameColor(square, targetSquare)) {
                    moves.push(coord);
                }

                break;
            }

            nextCol += dc;
            nextRow += dr;
        }
    });

    return moves;
}

function getRookMoves(square) {
    return getSlidingMoves(square, [
        [0, 1],
        [1, 0],
        [0, -1],
        [-1, 0],
    ]);
}

function getBishopMoves(square) {
    return getSlidingMoves(square, [
        [1, 1],
        [1, -1],
        [-1, -1],
        [-1, 1],
    ]);
}

function getQueenMoves(square) {
    return getSlidingMoves(square, [
        [0, 1],
        [1, 0],
        [0, -1],
        [-1, 0],
        [1, 1],
        [1, -1],
        [-1, -1],
        [-1, 1],
    ]);
}

function getKingMoves(square) {
    const { col, row } = coordToPosition(square.dataset.coord);
    const color = square.dataset.color;

    const moves = [
        [0, 1],
        [1, 1],
        [1, 0],
        [1, -1],
        [0, -1],
        [-1, -1],
        [-1, 0],
        [-1, 1],
    ]
        .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
        .filter(coord => coord !== null);

    return moves.concat(getCastlingMoves(square));
}

function getSquare(coord) {
    return document.querySelector(`[data-coord="${coord}"]`);
}

function getEnemyColor(color) {
    return color === 'white' ? 'black' : 'white';
}

function isSquareAttacked(coord, byColor) {
    const squares = document.querySelectorAll('.square');

    for (const square of squares) {
        if (square.dataset.color !== byColor) {
            continue;
        }

        const attackedCoords = getAttackedSquares(square);

        if (attackedCoords.includes(coord)) {
            return true;
        }
    }

    return false;
}

function getAttackedSquares(square) {
    const type = square.dataset.type;
    const color = square.dataset.color;
    const { col, row } = coordToPosition(square.dataset.coord);

    if (type === 'pawn') {
        const direction = color === 'white' ? 1 : -1;

        return [
            positionToCoord(col - 1, row + direction),
            positionToCoord(col + 1, row + direction),
        ].filter(coord => coord !== null);
    }

    if (type === 'horse') {
        return getHorseMoves(square);
    }

    if (type === 'bishop') {
        return getBishopMoves(square);
    }

    if (type === 'rook') {
        return getRookMoves(square);
    }

    if (type === 'queen') {
        return getQueenMoves(square);
    }

    if (type === 'king') {
        const moves = [
            [0, 1],
            [1, 1],
            [1, 0],
            [1, -1],
            [0, -1],
            [-1, -1],
            [-1, 0],
            [-1, 1],
        ];

        return moves
            .map(([dc, dr]) => positionToCoord(col + dc, row + dr))
            .filter(coord => coord !== null);
    }

    return [];
}

function getCastlingMoves(square) {
    const moves = [];
    const color = square.dataset.color;
    const enemyColor = getEnemyColor(color);

    const kingStart = color === 'white' ? 'e1' : 'e8';
    const row = color === 'white' ? '1' : '8';

    if (square.dataset.coord !== kingStart) {
        return moves;
    }

    if (castlingRights[color].kingMoved) {
        return moves;
    }

    if (isSquareAttacked(kingStart, enemyColor)) {
        return moves;
    }

    // Roque curto: rei para a direita
    const shortRookCoord = `h${row}`;
    const shortRook = getSquare(shortRookCoord);

    if (
        !castlingRights[color].rightRookMoved &&
        shortRook.dataset.type === 'rook' &&
        shortRook.dataset.color === color &&
        getSquare(`f${row}`).dataset.color === '' &&
        getSquare(`g${row}`).dataset.color === '' &&
        !isSquareAttacked(`f${row}`, enemyColor) &&
        !isSquareAttacked(`g${row}`, enemyColor)
    ) {
        moves.push(`g${row}`);
    }

    // Roque longo: rei para a esquerda
    const longRookCoord = `a${row}`;
    const longRook = getSquare(longRookCoord);

    if (
        !castlingRights[color].leftRookMoved &&
        longRook.dataset.type === 'rook' &&
        longRook.dataset.color === color &&
        getSquare(`b${row}`).dataset.color === '' &&
        getSquare(`c${row}`).dataset.color === '' &&
        getSquare(`d${row}`).dataset.color === '' &&
        !isSquareAttacked(`d${row}`, enemyColor) &&
        !isSquareAttacked(`c${row}`, enemyColor)
    ) {
        moves.push(`c${row}`);
    }

    return moves;
}

function getCSRFToken() {
    const cookies = document.cookie.split(';');

    for (let cookie of cookies) {
        cookie = cookie.trim();

        if (cookie.startsWith('csrftoken=')) {
            return cookie.substring('csrftoken='.length);
        }
    }

    return '';
}

function saveMoveToDatabase(moveData, gameState = {}) {
    if (typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE) {
        return;
    }
    if (isComputerMode()) {
        return;
    }

    const payload = {
        ...moveData,
        game_finished: Boolean(gameState.finished),
        winner: gameState.winner,
        result: gameState.result,
    };

    fetch(`/games/${GAME_ID}/save-move/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify(payload),
    })
    .then(response => {
        if (!response.ok) {
            syncMovesFromServer();
            throw new Error('Movimento recusado pelo servidor.');
        }

        return response.json();
    })
    .then(data => {
        console.log('Movimento salvo:', data);
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);
    })
    .catch(error => {
        console.error('Erro ao salvar movimento:', error);
    });
}

function syncFinishedGame(winner, options = {}) {
    if (
        finishedGameSynced ||
        typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE ||
        isComputerMode()
    ) {
        return;
    }

    finishedGameSynced = true;

    fetch(`/games/${GAME_ID}/mark-finished/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
        body: JSON.stringify({
            winner: winner,
            reason: options.reason || null,
            loser: options.loser || null,
            result: options.result || null,
        }),
    })
    .then(response => response.ok ? response.json() : Promise.reject(response))
    .then(data => {
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);
    })
    .catch(error => {
        finishedGameSynced = false;
        timeoutSyncInProgress = false;
        console.error('Erro ao finalizar partida:', error);
    });
}

function clearBoard() {
    document.querySelectorAll('.square').forEach(square => {
        square.replaceChildren();
        square.dataset.color = '';
        square.dataset.type = '';
    });
}

function setupInitialPosition() {
    clearBoard();

    Object.entries(initialPosition).forEach(([coord, position]) => {
        const square = getSquare(coord);

        square.appendChild(createPieceElement(position));
        square.dataset.color = position.color;
        square.dataset.type = position.type;
    });
}

function applyMoveWithoutSaving(move) {
    const promotionType = move.promotion || 'queen';
    const fromSquare = getSquare(move.from);
    const toSquare = getSquare(move.to);
    const movingType = move.piece_type;
    const movingColor = move.piece_color;

    if (
        movingType === 'pawn' &&
        move.from[0] !== move.to[0] &&
        toSquare.dataset.color === ''
    ) {
        const capturedPawnCoord = move.to[0] + move.from[1];
        const capturedPawnSquare = getSquare(capturedPawnCoord);

        capturedPawnSquare.replaceChildren();
        capturedPawnSquare.dataset.color = '';
        capturedPawnSquare.dataset.type = '';
    }

    if (
        movingType === 'king' &&
        Math.abs(getCol(move.from) - getCol(move.to)) === 2
    ) {
        const row = movingColor === 'white' ? '1' : '8';

        if (move.to === `g${row}`) {
            movePiece(getSquare(`h${row}`), getSquare(`f${row}`));
        }

        if (move.to === `c${row}`) {
            movePiece(getSquare(`a${row}`), getSquare(`d${row}`));
        }
    }

    movePiece(fromSquare, toSquare);
    // promoção automática
    if (isPromotionMove(movingType, movingColor, move.to)) {
        promotePawn(toSquare, movingColor, promotionType);
    }

    updateCastlingRightsAfterMove(move);
}

function loadPositionUntil(index) {
    index = Math.max(0, Math.min(index, SAVED_MOVES.length));

    clearSelection();
    setupInitialPosition();
    resetCastlingRights();

    for (let i = 0; i < index; i++) {
        applyMoveWithoutSaving(SAVED_MOVES[i]);
    }

    historyIndex = index;
    moveNumber = SAVED_MOVES.length + 1;
    currentTurn = index % 2 === 0 ? 'white' : 'black';
    lastMove = index > 0 ? SAVED_MOVES[index - 1] : null;

    refreshGameStatus();
    updateTurnIndicator();
    updateHistoryControls();
    updateCapturedMaterial();
}

function movesAreEqual(firstMove, secondMove) {
    return firstMove &&
        secondMove &&
        firstMove.move_number === secondMove.move_number &&
        firstMove.from === secondMove.from &&
        firstMove.to === secondMove.to &&
        firstMove.piece_type === secondMove.piece_type &&
        firstMove.piece_color === secondMove.piece_color &&
        (firstMove.promotion || null) === (secondMove.promotion || null);
}

async function syncMovesFromServer() {
    if (
        typeof GAME_ID === 'undefined' ||
        typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE ||
        isComputerMode() ||
        promotionPending
    ) {
        return;
    }

    try {
        const response = await fetch(`/games/${GAME_ID}/moves/`);

        if (!response.ok) {
            return;
        }

        const data = await response.json();
        applyClockState(data.clock);
        applyDrawOfferState(data.draw_offer);
        showServerGameResult(data);

        if (data.game_finished) {
            gameOver = true;

            if (data.winner === 'white' || data.winner === 'black') {
                showGameStatus(data.winner === 'white' ? 'Vitória das brancas' : 'Vitória das pretas');
            }
        }

        const serverMoves = data.moves || [];
        const hasDifferentMoves = serverMoves.length !== SAVED_MOVES.length ||
            serverMoves.some((move, index) => !movesAreEqual(move, SAVED_MOVES[index]));

        if (!hasDifferentMoves) {
            return;
        }

        SAVED_MOVES.splice(0, SAVED_MOVES.length, ...serverMoves);
        renderSavedMoveList();
        loadPositionUntil(SAVED_MOVES.length);
    } catch (error) {
        console.error('Erro ao sincronizar movimentos:', error);
    }
}

function renderSavedMoveList() {
    moveList.replaceChildren();

    SAVED_MOVES.forEach((move, index) => {
        const moveItem = document.createElement('li');
        moveItem.innerText = `${move.move_number}. ${move.from} -> ${move.to}`;
        moveItem.style.cursor = 'pointer';

        moveItem.addEventListener('click', function () {
            loadPositionUntil(index + 1);
        });

        moveList.appendChild(moveItem);
    });

    updatePgnBox();
}

function enableComputerEloSelect() {
    const eloSelect = document.getElementById('computer-elo');
    const playerColorSelect = document.getElementById('player-color');

    if (eloSelect) {
        eloSelect.disabled = analysisMode || SAVED_MOVES.length > 0;
    }

    if (playerColorSelect) {
        playerColorSelect.disabled = computerThinking || SAVED_MOVES.length > 0;
    }

    updateHistoryControls();
}

function undoComputerMove() {
    if (!isComputerMode() || computerThinking || SAVED_MOVES.length === 0) {
        return;
    }

    if (!confirm('Tem certeza de que deseja voltar sua última jogada?')) {
        return;
    }

    const movesToRemove = SAVED_MOVES.length % 2 === 0 ? 2 : 1;
    SAVED_MOVES.splice(Math.max(0, SAVED_MOVES.length - movesToRemove), movesToRemove);
    gameOver = false;
    setCoachComment(coachEnabled ? 'Treinador habilitado. Vou comentar suas jogadas.' : '');
    loadPositionUntil(SAVED_MOVES.length);
    renderSavedMoveList();
    enableComputerEloSelect();

    if (currentTurn === computerColor()) {
        askComputerMove();
    }
}

function resetComputerGame() {
    if (!isComputerMode() || computerThinking || SAVED_MOVES.length === 0) {
        return;
    }

    if (!confirm('Tem certeza de que deseja reiniciar a partida?')) {
        return;
    }

    SAVED_MOVES.splice(0, SAVED_MOVES.length);
    gameOver = false;
    finishedGameSynced = false;
    setCoachComment('');
    loadPositionUntil(0);
    renderSavedMoveList();
    enableComputerEloSelect();

    if (currentTurn === computerColor()) {
        askComputerMove();
    }
}

function toggleCoach() {
    coachEnabled = !coachEnabled;
    updateHistoryControls();

    if (coachEnabled) {
        setCoachComment('Treinador habilitado. Vou comentar suas jogadas.');
    } else {
        setCoachComment('');
    }
}

function setCoachComment(message) {
    const coachComment = document.getElementById('coach-comment');

    if (!coachComment) {
        return;
    }

    coachComment.innerText = message;
    coachComment.hidden = message === '';
}

function addTrainerChatMessage(message, type) {
    const log = document.getElementById('trainer-chat-log');

    if (!log) {
        return;
    }

    const item = document.createElement('div');
    item.classList.add('trainer-chat-message', `trainer-chat-message-${type}`);
    item.innerText = message;
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
}

function updateTrainerChatControls() {
    const submitButton = document.getElementById('trainer-chat-submit');
    const input = document.getElementById('trainer-chat-input');

    if (submitButton) {
        submitButton.disabled = trainerChatThinking;
        submitButton.innerText = trainerChatThinking ? 'Pensando...' : 'Perguntar';
    }

    if (input) {
        input.disabled = trainerChatThinking;
    }
}

function trainerChatMoves() {
    if (typeof ANALYZER_MODE !== 'undefined' && ANALYZER_MODE) {
        return SAVED_MOVES.slice(0, historyIndex);
    }

    return SAVED_MOVES;
}

async function askTrainerChat(question) {
    trainerChatThinking = true;
    updateTrainerChatControls();
    addTrainerChatMessage(question, 'user');

    try {
        const response = await fetch('/trainer-chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                question: question,
                moves: trainerChatMoves(),
                player_color: playerColor(),
            }),
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            console.error('Erro do chat do treinador:', data.error || response.statusText);
            addTrainerChatMessage('Não consegui responder agora. Tente perguntar de outro jeito.', 'trainer');
            return;
        }

        addTrainerChatMessage(data.answer, 'trainer');
    } catch (error) {
        console.error('Erro ao perguntar ao treinador:', error);
        addTrainerChatMessage('Não consegui responder agora. Tente novamente em instantes.', 'trainer');
    } finally {
        trainerChatThinking = false;
        updateTrainerChatControls();
    }
}

async function requestCoachAnalysis() {
    setCoachComment('Treinador analisando...');

    try {
        const response = await fetch('/coach-analysis/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                moves: SAVED_MOVES,
                player_color: playerColor(),
            }),
        });

        const analysis = await response.json();

        if (!response.ok || analysis.error) {
            console.error('Erro do treinador:', analysis.error || response.statusText);
            setCoachComment('O treinador não conseguiu analisar esta jogada.');
            return;
        }

        setCoachComment(analysis.comment || '');
    } catch (error) {
        console.error('Erro ao pedir análise do treinador:', error);
        setCoachComment('O treinador não conseguiu analisar esta jogada.');
    }
}

document.getElementById('prev-move').addEventListener('click', function () {
    if (historyIndex > 0) {
        loadPositionUntil(historyIndex - 1);
    }
});

document.getElementById('next-move').addEventListener('click', function () {
    if (historyIndex < SAVED_MOVES.length) {
        loadPositionUntil(historyIndex + 1);
    }
});

document.getElementById('last-move').addEventListener('click', function () {
    loadPositionUntil(SAVED_MOVES.length);
});

const undoComputerButton = document.getElementById('undo-computer-move');
if (undoComputerButton) {
    undoComputerButton.addEventListener('click', undoComputerMove);
}

const resetComputerButton = document.getElementById('reset-computer-game');
if (resetComputerButton) {
    resetComputerButton.addEventListener('click', resetComputerGame);
}

const toggleCoachButton = document.getElementById('toggle-coach');
if (toggleCoachButton) {
    toggleCoachButton.addEventListener('click', toggleCoach);
}

const flipBoardButton = document.getElementById('flip-board');
if (flipBoardButton) {
    flipBoardButton.addEventListener('click', flipBoard);
}

if (offerDrawButton) {
    offerDrawButton.addEventListener('click', async function () {
        offerDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/offer-draw/`);
        } catch (error) {
            console.error('Erro ao oferecer empate:', error);
        } finally {
            offerDrawButton.disabled = gameOver;
        }
    });
}

if (acceptDrawButton) {
    acceptDrawButton.addEventListener('click', async function () {
        acceptDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/answer-draw/`, { accepted: true });
        } catch (error) {
            console.error('Erro ao aceitar empate:', error);
            acceptDrawButton.disabled = false;
        }
    });
}

if (rejectDrawButton) {
    rejectDrawButton.addEventListener('click', async function () {
        rejectDrawButton.disabled = true;

        try {
            await postGameAction(`/games/${GAME_ID}/answer-draw/`, { accepted: false });
        } catch (error) {
            console.error('Erro ao recusar empate:', error);
        } finally {
            rejectDrawButton.disabled = false;
        }
    });
}

if (resignButton) {
    resignButton.addEventListener('click', function () {
        showResignConfirmPanel();
    });
}

if (cancelResignButton) {
    cancelResignButton.addEventListener('click', function () {
        hideResignConfirmPanel();
    });
}

if (confirmResignButton) {
    confirmResignButton.addEventListener('click', async function () {
        confirmResignButton.disabled = true;

        if (resignButton) {
            resignButton.disabled = true;
        }

        try {
            await postGameAction(`/games/${GAME_ID}/resign/`);
            hideResignConfirmPanel();
        } catch (error) {
            console.error('Erro ao desistir:', error);
            confirmResignButton.disabled = false;
            if (resignButton) {
                resignButton.disabled = false;
            }
        }
    });
}

const analysisModeButton = document.getElementById('toggle-analysis-mode');
if (analysisModeButton) {
    analysisModeButton.addEventListener('click', toggleAnalysisMode);
}

const analysisPrevButton = document.getElementById('analysis-prev');
if (analysisPrevButton) {
    analysisPrevButton.addEventListener('click', showPreviousAnalysisPosition);
}

const analysisNextButton = document.getElementById('analysis-next');
if (analysisNextButton) {
    analysisNextButton.addEventListener('click', showNextAnalysisPosition);
}

const playerColorSelect = document.getElementById('player-color');
if (playerColorSelect) {
    playerColorSelect.value = playerColor();
    playerColorSelect.addEventListener('change', function () {
        if (!isComputerMode() || SAVED_MOVES.length > 0 || computerThinking) {
            playerColorSelect.value = playerColor();
            return;
        }

        PLAYER_COLOR = playerColorSelect.value;
        boardOrientation = playerColor();
        updateBoardOrientation();
        updateTurnIndicator();
        updateHistoryControls();

        if (currentTurn === computerColor()) {
            askComputerMove();
        }
    });
}

const trainerChatForm = document.getElementById('trainer-chat-form');
if (trainerChatForm) {
    trainerChatForm.addEventListener('submit', function (event) {
        event.preventDefault();

        const input = document.getElementById('trainer-chat-input');
        const question = input ? input.value.trim() : '';

        if (!question || trainerChatThinking) {
            return;
        }

        input.value = '';
        askTrainerChat(question);
    });
}


function updatePgnBox() {
    const moves = Array.from(moveList.children)
        .map(item => item.innerText)
        .join('\n');

    pgnBox.innerText = moves;
}

function choosePromotionPiece(square, color) {
    promotionPending = true;

    document.querySelectorAll('.promotion-selector').forEach(selector => {
        selector.remove();
    });

    const selector = document.createElement('div');
    selector.classList.add('promotion-selector');

    if (getCol(square.dataset.coord) >= 4) {
        selector.classList.add('promotion-selector-left');
    }

    selector.addEventListener('click', function (event) {
        event.stopPropagation();
    });

    const options = [
        { type: 'queen', label: 'Dama' },
        { type: 'rook', label: 'Torre' },
        { type: 'bishop', label: 'Bispo' },
        { type: 'horse', label: 'Cavalo' },
    ];

    return new Promise(resolve => {
        options.forEach(option => {
            const button = document.createElement('button');
            button.type = 'button';
            button.classList.add('promotion-option');
            button.title = option.label;
            button.setAttribute('aria-label', option.label);
            button.appendChild(createPieceElement({
                type: option.type,
                color: color
            }));

            button.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                selector.remove();
                promotionPending = false;
                resolve(option.type);
            });

            selector.appendChild(button);
        });

        square.appendChild(selector);
    });
}

async function askComputerMove() {
    if (gameOver || currentTurn !== computerColor() || computerThinking) {
        return;
    }

    computerThinking = true;
    updateTurnIndicator();
    updateHistoryControls();

    const eloSelect = document.getElementById('computer-elo');
    const elo = eloSelect ? eloSelect.value : 1200;

    let move;

    try {
        const response = await fetch('/engine-move/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                moves: SAVED_MOVES,
                elo: elo,
            }),
        });

        move = await response.json();

        if (!response.ok || move.error) {
            console.error('Erro do computador:', move.error || response.statusText);
            computerThinking = false;
            updateTurnIndicator();
            updateHistoryControls();
            return;
        }
    } catch (error) {
        console.error('Erro ao pedir jogada do computador:', error);
        computerThinking = false;
        updateTurnIndicator();
        updateHistoryControls();
        return;
    }

    const fromSquare = getSquare(move.from);
    const toSquare = getSquare(move.to);

    if (!fromSquare || !toSquare) {
        computerThinking = false;
        updateTurnIndicator();
        updateHistoryControls();
        return;
    }

    await playMove(fromSquare, toSquare, true, move.promotion || null);
    computerThinking = false;
    updateTurnIndicator();
    updateHistoryControls();
}
