/**
 * Asset Modal Helper
 * Opens asset details in a modal popup
 */

async function openAssetModal(assetId) {
    try {
        const response = await fetch(`/asset_management/view/${assetId}`);
        if (!response.ok) {
            throw new Error('Failed to load asset details');
        }
        
        const html = await response.text();
        
        // Create a temporary container
        const container = document.createElement('div');
        container.innerHTML = html;
        
        // Append modal to body
        document.body.appendChild(container.firstElementChild);
        
        // Prevent body scroll when modal is open
        document.body.style.overflow = 'hidden';
        
        // Re-enable scroll when modal is closed
        const modal = document.getElementById('assetModal');
        const observer = new MutationObserver(() => {
            if (!document.getElementById('assetModal')) {
                document.body.style.overflow = 'auto';
                observer.disconnect();
            }
        });
        
        observer.observe(document.body, { childList: true });
        
    } catch (error) {
        console.error('Error opening asset modal:', error);
        alert('Failed to load asset details. Please try again.');
    }
}

// Close modal function (can be called from anywhere)
function closeAssetModal() {
    const modal = document.getElementById('assetModal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}
