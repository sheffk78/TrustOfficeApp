import { useState, useEffect, useCallback, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Download, ExternalLink, FileText, X, AlertCircle, RefreshCw } from 'lucide-react';

/**
 * PDFPreviewModal - A robust PDF preview component for TrustOffice
 * 
 * Uses Blob URLs for better browser compatibility compared to data: URLs.
 * Includes fallbacks for mobile and unsupported browsers.
 * 
 * @param {boolean} open - Controls modal visibility
 * @param {function} onOpenChange - Callback when modal state changes
 * @param {string} pdfBase64 - Base64-encoded PDF data
 * @param {string} title - Modal title (default: "PDF Preview")
 * @param {string} filename - Filename for download (default: "document.pdf")
 */
export function PDFPreviewModal({ 
  open, 
  onOpenChange, 
  pdfBase64, 
  title = "PDF Preview",
  filename = "document.pdf"
}) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [previewError, setPreviewError] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const iframeRef = useRef(null);
  const loadTimeoutRef = useRef(null);

  // Detect mobile devices
  useEffect(() => {
    const checkMobile = () => {
      const mobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      setIsMobile(mobile);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Convert base64 to Blob URL when PDF data changes
  useEffect(() => {
    if (!pdfBase64 || !open) {
      setBlobUrl(null);
      setPreviewError(false);
      setIsLoading(true);
      setIframeLoaded(false);
      if (loadTimeoutRef.current) {
        clearTimeout(loadTimeoutRef.current);
      }
      return;
    }

    try {
      // Decode base64 to binary
      const byteCharacters = atob(pdfBase64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      
      // Create Blob and URL
      const blob = new Blob([byteArray], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      setBlobUrl(url);
      setIsLoading(false);
      setPreviewError(false);
      setIframeLoaded(false);
      
      // Set a timeout to detect if iframe fails to load (security restrictions)
      // If iframe doesn't report loaded within 3 seconds, show fallback
      loadTimeoutRef.current = setTimeout(() => {
        if (!iframeLoaded) {
          setPreviewError(true);
        }
      }, 3000);
      
    } catch (error) {
      console.error('Failed to create PDF blob:', error);
      setPreviewError(true);
      setIsLoading(false);
    }

    // Cleanup blob URL when component unmounts or PDF changes
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
      if (loadTimeoutRef.current) {
        clearTimeout(loadTimeoutRef.current);
      }
    };
  }, [pdfBase64, open]);

  // Download PDF
  const handleDownload = useCallback(() => {
    if (!pdfBase64) return;
    
    try {
      const byteCharacters = atob(pdfBase64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
    }
  }, [pdfBase64, filename]);

  // Open in new tab (useful for mobile)
  const handleOpenInNewTab = useCallback(() => {
    if (!blobUrl && !pdfBase64) return;
    
    try {
      // Create a fresh blob URL for the new tab
      const byteCharacters = atob(pdfBase64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      
      window.open(url, '_blank');
    } catch (error) {
      console.error('Failed to open in new tab:', error);
    }
  }, [blobUrl, pdfBase64]);

  // Handle iframe load success
  const handleIframeLoad = useCallback(() => {
    setIframeLoaded(true);
    if (loadTimeoutRef.current) {
      clearTimeout(loadTimeoutRef.current);
    }
  }, []);

  // Handle iframe load error
  const handleIframeError = () => {
    setPreviewError(true);
    if (loadTimeoutRef.current) {
      clearTimeout(loadTimeoutRef.current);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent 
        className="max-w-4xl w-[95vw] h-[90vh] flex flex-col p-0 gap-0 rounded-none border border-navy/20 dark:border-gold/20"
        data-testid="pdf-preview-modal"
      >
        {/* Header */}
        <DialogHeader className="px-6 py-4 border-b border-navy/10 dark:border-white/10 flex-shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="font-serif text-xl text-navy dark:text-gold">
              {title}
            </DialogTitle>
            <div className="flex items-center gap-2">
              {/* Open in New Tab - always show */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenInNewTab}
                className="font-mono text-xs uppercase tracking-widest"
                data-testid="pdf-open-new-tab-btn"
              >
                <ExternalLink className="w-4 h-4 mr-2" />
                Open in Tab
              </Button>
              
              {/* Download button */}
              <Button
                onClick={handleDownload}
                size="sm"
                className="btn-primary font-mono text-xs uppercase tracking-widest"
                data-testid="pdf-download-btn"
              >
                <Download className="w-4 h-4 mr-2" />
                Download
              </Button>
              
              {/* Close button */}
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => onOpenChange(false)}
                data-testid="pdf-close-btn"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Content */}
        <div className="flex-1 bg-subtle-bg dark:bg-slate-900 overflow-hidden relative">
          {isLoading ? (
            // Loading state
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <RefreshCw className="w-12 h-12 text-navy/30 dark:text-gold/30 animate-spin mb-4" />
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Loading PDF...
              </p>
            </div>
          ) : isMobile || previewError ? (
            // Mobile or Error Fallback
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <FileText className="w-16 h-16 text-navy/30 dark:text-gold/30 mb-4" />
              
              {previewError ? (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertCircle className="w-5 h-5 text-gold" />
                    <p className="font-mono text-sm uppercase tracking-widest text-navy dark:text-gold">
                      Preview Unavailable
                    </p>
                  </div>
                  <p className="text-muted-foreground text-sm mb-6 max-w-md">
                    Your browser's security settings prevent inline PDF preview. 
                    Use the buttons above to view or download the document.
                  </p>
                </>
              ) : (
                <>
                  <p className="font-mono text-sm uppercase tracking-widest text-navy dark:text-gold mb-2">
                    Mobile Device Detected
                  </p>
                  <p className="text-muted-foreground text-sm mb-6 max-w-md">
                    For the best experience, open the PDF in a new tab or download it to your device.
                  </p>
                </>
              )}
              
              <div className="flex flex-col sm:flex-row gap-3">
                <Button
                  onClick={handleOpenInNewTab}
                  variant="outline"
                  className="font-mono text-xs uppercase tracking-widest"
                  data-testid="pdf-fallback-open-btn"
                >
                  <ExternalLink className="w-4 h-4 mr-2" />
                  Open in New Tab
                </Button>
                <Button
                  onClick={handleDownload}
                  className="btn-primary font-mono text-xs uppercase tracking-widest"
                  data-testid="pdf-fallback-download-btn"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Download PDF
                </Button>
              </div>
            </div>
          ) : (
            // Desktop PDF Preview using iframe with blob URL
            <iframe
              ref={iframeRef}
              src={blobUrl}
              className="w-full h-full border-0"
              title={title}
              onLoad={handleIframeLoad}
              onError={handleIframeError}
              data-testid="pdf-iframe-preview"
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default PDFPreviewModal;
