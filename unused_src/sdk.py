__author__ = 'paulp'

sx = 9
sy = 9
numblks = sx * sy

board = numblks * [[]]
possibles = numblks * [range(0, sx)]
values = numblks * [-1]

values = [
    6,   5, -1, -1, -1, -1, -1, -1,  9,
    -1, -1, -1, -1, -1,  7,  5, -1,  1,
    -1,  7,  3, -1, -1,  5,  4, -1, -1,
    -1,  4,  9, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1,  5, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1,  2,  6, -1,
    -1, -1,  6,  8, -1, -1,  7,  1, -1,
    7,  -1,  1,  4, -1, -1, -1, -1, -1,
    4,  -1, -1, -1, -1, -1, -1,  9,  8
]

def row_col_cell_from_index(idx):
    r = int(idx / sx)
    c = idx - (r * sx)
    cellc = int(r/3)
    cellr = int(c/3)
    return r, c, cellr + (3*cellc)


def idxs_in_row(r):
    return range(r * sx, (r+1) * sx)


def idxs_in_col(c):
    return range(c, numblks, sx)


def idxs_in_cell(cell):
    start_idx = ((cell/3)*27) + ((cell%3)*3)
    rv = range(start_idx, start_idx + 3)
    start_idx += 9
    rv.extend(range(start_idx, start_idx + 3))
    start_idx += 9
    rv.extend(range(start_idx, start_idx + 3))
    return rv

# set up the board
for idx in range(0, numblks):
    r, c, cell = row_col_cell_from_index(idx)
    rowmates = idxs_in_row(r)
    colmates = idxs_in_col(c)
    cellmates = idxs_in_cell(cell)
    for l in [rowmates, colmates, cellmates]:
        l.pop(l.index(idx))
    board[idx] = [r, c, cell, rowmates, colmates, cellmates]
    try:
        print values[idx]
        print possibles[idx]
        possibles[idx].pop(possibles[idx].index(values[idx]))
    except ValueError:
        pass

print possibles