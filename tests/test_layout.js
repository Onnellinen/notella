import {slots, WIDTH, HEIGHT, GAP} from '../gnome-extension/layout.js';

function assert(value, description) {
    if (!value)
        throw new Error(description);
}

const area = {x: 80, y: 30, width: 1920, height: 1050};
const positions = slots(area);
assert(positions.length === 15, '1920x1050 fits 5 columns of 3 notes');
assert(positions[0].x === 1648 && positions[0].y === 42, 'First note is top right');
assert(positions[1].x === 1648 && positions[1].y === 314, 'Second note is below first');
assert(positions[3].x === 1296 && positions[3].y === 42, 'Next column starts to the left');
for (const [index, position] of positions.entries()) {
    assert(position.width === 340 && position.height === 260, 'Fixed logical-pixel size');
    assert(position.x >= area.x + GAP && position.y >= area.y + GAP, 'Inside top and left');
    assert(position.x + WIDTH <= area.x + area.width - GAP, 'Inside right margin');
    assert(position.y + HEIGHT <= area.y + area.height - GAP, 'Inside bottom margin');
    for (const other of positions.slice(index + 1)) {
        assert(position.x + WIDTH <= other.x || other.x + WIDTH <= position.x ||
            position.y + HEIGHT <= other.y || other.y + HEIGHT <= position.y, 'No overlap');
    }
}
assert(slots({x: 0, y: 0, width: 363, height: 284}).length === 0, 'Width threshold');
assert(slots({x: 0, y: 0, width: 364, height: 283}).length === 0, 'Height threshold');
assert(slots({x: 0, y: 0, width: 364, height: 284}).length === 1, 'Exact minimum fits');
assert(slots({x: 0, y: 0, width: 0, height: 0}).length === 0, 'No work area');
assert(slots({x: -1000, y: -500, width: 364, height: 284})[0].x === -988,
    'Negative monitor coordinates');
print('PASS: desktop layout, fixed size, column wrapping, capacity thresholds and non-overlap');
