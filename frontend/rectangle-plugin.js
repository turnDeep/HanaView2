/**
 * lightweight-charts v5対応 Rectangle Primitive
 * Series Primitive として実装
 */
class RectanglePrimitive {
    constructor(options) {
        this._options = options;
        this._source = null;
        this._requestUpdate = null;
    }

    attached(param) {
        this._source = param;
        this._requestUpdate = param.requestUpdate;
    }

    detached() {
        this._source = null;
        this._requestUpdate = null;
    }

    paneViews() {
        return [new RectanglePaneView(this._options, this._source)];
    }

    updateAllViews() {
        // 必要に応じて更新をリクエスト
    }
}

class RectanglePaneView {
    constructor(options, source) {
        this._options = options;
        this._source = source;
    }

    update() {
        // ビューの更新
    }

    renderer() {
        return new RectanglePaneRenderer(this._options, this._source);
    }

    zOrder() {
        return 'normal';
    }
}

class RectanglePaneRenderer {
    constructor(options, source) {
        this._options = options;
        this._source = source;
    }

    draw(target) {
        if (!this._source) return;

        const { series, chart } = this._source;
        const timeScale = chart.timeScale();
        const priceScale = series.priceScale();

        const p1 = this._options.points[0];
        const p2 = this._options.points[1];

        // 座標変換
        const x1 = timeScale.timeToCoordinate(p1.time);
        const y1 = priceScale.priceToCoordinate(p1.price);
        const x2 = timeScale.timeToCoordinate(p2.time);
        const y2 = priceScale.priceToCoordinate(p2.price);

        if (x1 === null || x2 === null || y1 === null || y2 === null) {
            return;
        }

        target.useBitmapCoordinateSpace(scope => {
            const ctx = scope.context;
            const scaledX = Math.min(x1, x2) * scope.horizontalPixelRatio;
            const scaledY = Math.min(y1, y2) * scope.verticalPixelRatio;
            const scaledWidth = Math.abs(x1 - x2) * scope.horizontalPixelRatio;
            const scaledHeight = Math.abs(y1 - y2) * scope.verticalPixelRatio;

            // 塗りつぶし
            ctx.fillStyle = this._options.fillColor || 'rgba(255, 215, 0, 0.2)';
            ctx.fillRect(scaledX, scaledY, scaledWidth, scaledHeight);

            // 境界線
            if (this._options.borderWidth > 0) {
                ctx.strokeStyle = this._options.borderColor || '#FFD700';
                ctx.lineWidth = this._options.borderWidth * scope.horizontalPixelRatio;
                ctx.strokeRect(scaledX, scaledY, scaledWidth, scaledHeight);
            }
        });
    }
}