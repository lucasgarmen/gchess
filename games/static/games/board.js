let lastMove = null;
let currentTurn = 'white';
let selectedSquare = null;
let moveNumber = 1;

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

function squareColor(square) {
    return square.dataset.color || '';
}

function sameColor(square1, square2) {
    return squareColor(square1) !== '' && squareColor(square1) === squareColor(square2);
}

function updateTurnIndicator() {
    turnIndicator.innerText = currentTurn === 'white'
        ? 'Vez das brancas'
        : 'Vez das pretas';
}

function selectSquare(square) {
    selectedSquare = square;
    square.classList.add('selected');

    const moves = getPossibleMoves(square);
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

function createPieceElement(position) {
    const pieceKey = `${position.type}_${position.color}`;
    const pieceImage = document.createElement('img');
    const fileName = pieceFileNames[pieceKey] || `${pieceKey}.png`;

    pieceImage.src = `/static/games/pieces/${fileName}`;
    pieceImage.alt = pieceKey;
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

        square.addEventListener('click', function () {
            if (selectedSquare === null) {
                if (squareColor(square) === currentTurn) {
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

                if (squareColor(square) === currentTurn) {
                    selectSquare(square);
                }

                return;
            }
            

           if (!isPossibleMove(square)) {
                return;
            }

            const movingType = selectedSquare.dataset.type;
            const movingColor = selectedSquare.dataset.color;

            const from = selectedSquare.dataset.coord;
            const to = square.dataset.coord;

            const moveItem = document.createElement('li');
            moveItem.innerText = `${moveNumber}. ${from} -> ${to}`;
            moveList.appendChild(moveItem);

            moveNumber++;

            // comer al paso
            if (
                movingType === 'pawn' &&
                selectedSquare.dataset.coord[0] !== square.dataset.coord[0] &&
                square.dataset.color === ''
            ) {
                const capturedPawnCoord = square.dataset.coord[0] + selectedSquare.dataset.coord[1];
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

            movePiece(selectedSquare, square);
            // marcar rey o torre como movidos
            if (movingType === 'king') {
                castlingRights[movingColor].kingMoved = true;
            }

            if (movingType === 'rook') {
                if (from === 'a1') castlingRights.white.leftRookMoved = true;
                if (from === 'h1') castlingRights.white.rightRookMoved = true;
                if (from === 'a8') castlingRights.black.leftRookMoved = true;
                if (from === 'h8') castlingRights.black.rightRookMoved = true;
            }
            lastMove = {
                from: from,
                to: to,
                type: movingType,
                color: movingColor
            };

            clearSelection();
            switchTurn();
        });

        board.appendChild(square);
    }
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

    // 1 casa adelante
    const frontCoord = positionToCoord(col, row + direction);

    if (frontCoord) {
        const frontSquare = document.querySelector(`[data-coord="${frontCoord}"]`);

        if (frontSquare.dataset.color === '') {
            moves.push(frontCoord);

            // 2 casas adelante desde posición inicial
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
            lastMove.type === 'pawn' &&
            lastMove.color !== color &&
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

        if (square && !sameColor(selectedSquare, square)) {
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

    // mover 1 casa para adelante
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

    // Enroque corto: rey hacia la derecha
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

    // Enroque largo: rey hacia la izquierda
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