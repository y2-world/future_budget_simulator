// ========================================
// 共通ユーティリティ関数
// ========================================

/**
 * モダンなトーストメッセージを表示
 * @param {string} message - 表示するメッセージ
 * @param {string} type - メッセージタイプ ('success', 'error', 'info')
 * @param {number} duration - 表示時間（ミリ秒）
 */
window.showToast = function(message, type = 'info', duration = 4000) {
    const backgrounds = {
        success: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        info: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'
    };

    Toastify({
        text: message,
        duration: duration,
        close: true,
        gravity: "top",
        position: "center",
        stopOnFocus: true,
        className: "modern-toast",
        style: {
            background: backgrounds[type] || backgrounds.info,
            borderRadius: "12px",
            padding: "16px 24px",
            fontSize: "15px",
            fontWeight: "500",
            boxShadow: "0 10px 25px rgba(0, 0, 0, 0.15), 0 4px 6px rgba(0, 0, 0, 0.1)",
        }
    }).showToast();
};

/**
 * CSRFトークンを取得
 * @returns {string} CSRFトークン
 */
window.getCSRFToken = function() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
};

/**
 * Ajax リクエストを送信（共通エラーハンドリング付き）
 * @param {string} url - リクエストURL
 * @param {FormData} formData - 送信するフォームデータ
 * @param {Object} options - オプション
 * @returns {Promise<Object>} レスポンスデータ
 */
window.sendAjaxRequest = async function(url, formData, options = {}) {
    const {
        method = 'POST',
        onSuccess = null,
        onError = null,
        showSuccessToast = true,
        showErrorToast = true,
        reloadOnSuccess = true,
        reloadDelay = 1500
    } = options;

    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'X-CSRFToken': window.getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            // 成功時の処理
            if (showSuccessToast) {
                window.showToast(data.message || '処理が完了しました。', 'success', 3000);
            }

            if (onSuccess) {
                onSuccess(data);
            }

            if (reloadOnSuccess) {
                setTimeout(() => window.location.reload(), reloadDelay);
            }

            return data;
        } else {
            // エラー時の処理
            if (showErrorToast) {
                window.showToast(data.message || 'エラーが発生しました。', 'error', 5000);
            }

            if (onError) {
                onError(data);
            }

            return data;
        }
    } catch (error) {
        console.error('Ajax request error:', error);

        if (showErrorToast) {
            window.showToast('サーバーとの通信中にエラーが発生しました。', 'error', 5000);
        }

        if (onError) {
            onError(error);
        }

        throw error;
    }
};

/**
 * Ajax レスポンスを処理（後方互換性のため）
 * @param {Object} response - レスポンスデータ
 */
window.handleAjaxResponse = function(response) {
    const message = response.message || (response.status === 'success' ? '処理が完了しました。' : 'エラーが発生しました。');
    const isSuccess = response.status === 'success';

    window.showToast(message, isSuccess ? 'success' : 'error', isSuccess ? 3000 : 5000);

    if (isSuccess) {
        setTimeout(() => window.location.reload(), 1500);
    }
};
