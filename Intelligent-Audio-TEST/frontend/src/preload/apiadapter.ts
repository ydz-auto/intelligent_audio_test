import { APIResponse, ErrorCode } from '../shared/types';

export class APIAdapter {
    static async request<T>(channel: string, ...args: any[]): Promise<APIResponse<T>> {
        try {
            // Assuming channel is the URL and first arg contains the request options
            const requestOptions = args[0] || {};
            const response = await window.electronAPI.apiRequest({
                url: channel,
                method: 'GET',
                ...requestOptions
            });
            
            if (response && typeof response.code === 'number') {
                return response as APIResponse<T>;
            }

            return {success: false, code: ErrorCode.SYSTEM_ERROR, message: 'Invalid response format from backend', detail: JSON.stringify(response)};
        } catch (error: any) {
            console.error(`[APIAdapter] Request failed on channel ${channel}:`, error);
            return {success: false, code: ErrorCode.NETWORK_ERROR, message: error.message || 'Network communication error', detail: error.stack};
        }
    }

    static handleCommonErrors(response: APIResponse) {
        if (response.code === ErrorCode.SUCCESS) return;

        switch (response.code) {
            case ErrorCode.UNAUTHORIZED:
                break;
            case ErrorCode.NOT_FOUND:
                console.warn('Resource not found:', response.message);
                break;
            default:
                console.error(`Business Error [${response.code}]:`, response.message);
        }
    }
}
