// ========================================
// 共通ユーティリティ関数
// ========================================

/**
 * モダンなトーストメッセージを表示
 * @param {string} message - 表示するメッセージ
 * @param {string} type - メッセージタイプ ('success', 'error', 'info')
 * @param {number} duration - 表示時間（ミリ秒）
 * @param {string} targetUrl - クリック時の遷移先URL（オプション）
 */
window.showToast = function(message, type = 'info', duration = 4000, targetUrl = null) {
    const backgrounds = {
        success: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        info: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'
    };

    const toastConfig = {
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
    };

    // URLが指定されている場合はクリック時に遷移
    if (targetUrl) {
        toastConfig.onClick = function() {
            window.location.href = targetUrl;
        };
        toastConfig.style.cursor = 'pointer';
    }

    Toastify(toastConfig).showToast();
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
        reloadDelay = 1500,
        closeModal = null  // モーダルを閉じる関数
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

        console.log('Response status:', response.status); // デバッグ用
        const data = await response.json();
        console.log('Response data:', data); // デバッグ用

        if (response.ok && data.status === 'success') {
            // モーダルを閉じる
            if (closeModal) {
                closeModal();
            }

            // 成功時の処理
            if (showSuccessToast) {
                // target_urlがある場合は遷移先URLを設定
                const targetUrl = data.target_url || null;
                window.showToast(data.message || '処理が完了しました。', 'success', 3000, targetUrl);
            }

            if (onSuccess) {
                onSuccess(data);
            }

            // target_urlがある場合は遷移、ない場合はリロード
            if (data.target_url) {
                // URLが指定されている場合は自動遷移（トーストをクリックしなくても遷移）
                setTimeout(() => window.location.href = data.target_url, reloadDelay);
            } else if (reloadOnSuccess) {
                setTimeout(() => window.location.reload(), reloadDelay);
            }

            return data;
        } else {
            // エラー時の処理
            console.log('Error response:', data); // デバッグ用
            console.log('Error data.errors:', data.errors); // エラー詳細をログ

            if (showErrorToast) {
                let errorMessage = '';

                // バリデーションエラーの詳細を表示
                if (data.errors && typeof data.errors === 'object') {
                    const errorMessages = [];

                    // フィールド名の日本語マッピング
                    const fieldLabels = {
                        'salary': '給与',
                        'bonus': 'ボーナス',
                        'food': '食費',
                        'rent': '家賃',
                        'lake': 'レイク返済',
                        'view_card': 'VIEWカード',
                        'view_card_bonus': 'VIEWボーナス払い',
                        'rakuten_card': '楽天カード',
                        'paypay_card': 'PayPayカード',
                        'vermillion_card': 'VERMILLION CARD',
                        'amazon_card': 'Amazonカード',
                        'loan': 'マネーアシスト返済',
                        'loan_borrowing': 'マネーアシスト借入',
                        'other': 'ジム',
                        'initial_balance': '初期残高',
                        'default_salary': 'デフォルト給与',
                        'default_food': 'デフォルト食費',
                        'default_view_card': 'VIEWカードデフォルト利用額',
                        'savings_amount': '定期預金額',
                        'savings_year': '定期預金開始年',
                        'savings_month': '定期預金開始月',
                        'year': '年',
                        'month': '月',
                        'year_month': '年月',
                        'card_type': 'カード種別',
                        'description': 'メモ',
                        'amount': '金額',
                        'due_date': '請求日',
                        'label': '項目名'
                    };

                    for (const [field, errors] of Object.entries(data.errors)) {
                        // フィールド名を日本語に変換
                        let fieldLabel = fieldLabels[field] || field;

                        // Djangoのフォームエラーは通常配列形式: {"field": ["エラー1", "エラー2"]}
                        if (Array.isArray(errors)) {
                            errors.forEach(error => {
                                // エラーがオブジェクト形式の場合（例: {message: "エラー内容"}）
                                const errorText = typeof error === 'object' ? (error.message || JSON.stringify(error)) : error;
                                errorMessages.push(`【${fieldLabel}】${errorText}`);
                            });
                        } else if (typeof errors === 'string') {
                            // 文字列の場合
                            errorMessages.push(`【${fieldLabel}】${errors}`);
                        } else {
                            // その他のオブジェクト形式
                            errorMessages.push(`【${fieldLabel}】${JSON.stringify(errors)}`);
                        }
                    }
                    if (errorMessages.length > 0) {
                        errorMessage = errorMessages.join('\n');
                    }
                }

                // エラーメッセージがない場合はデフォルトメッセージを使用
                if (!errorMessage) {
                    errorMessage = data.message || 'エラーが発生しました。入力内容を確認してください。';
                }

                console.log('Final error message:', errorMessage); // デバッグ用
                window.showToast(errorMessage, 'error', 6000);
            }

            if (onError) {
                onError(data);
            }

            return data;
        }
    } catch (error) {
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
