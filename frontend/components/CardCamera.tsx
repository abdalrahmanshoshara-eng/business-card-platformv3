'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Orientation, Rect, guideRect, guideToVideoRect, outputSize } from '@/features/camera/frame';

type Props = {
  open: boolean;
  title: string;
  /** File name prefix for the captured photo, e.g. "card-front". */
  fileName: string;
  onCapture: (file: File) => void;
  onClose: () => void;
  /** Live camera unavailable or denied: use the device camera app instead.
   *  Only ever called from a tap, so the file input it opens is not blocked. */
  onFallback: () => void;
};

/** Live camera needs getUserMedia, which browsers expose only on HTTPS / localhost. */
export function liveCameraSupported(): boolean {
  return typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
}

/**
 * Live camera with a card-shaped guide. The photo is cropped to the guide (plus
 * a small margin), so the extractor gets the card rather than the whole desk.
 */
export default function CardCamera({ open, title, fileName, onCapture, onClose, onFallback }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [orientation, setOrientation] = useState<Orientation>('landscape');
  const [guide, setGuide] = useState<Rect | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  // Start / stop the camera with the dialog.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    if (!liveCameraSupported()) {
      setError('الكاميرا المباشرة غير مدعومة على هذا المتصفح.');
      return;
    }
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      .then(stream => {
        if (cancelled) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((err: DOMException) => {
        if (cancelled) return;
        setError(
          err?.name === 'NotAllowedError'
            ? 'لم يُسمح بالوصول إلى الكاميرا. اسمح بالوصول من إعدادات المتصفح أو استخدم كاميرا الجهاز.'
            : 'تعذّر تشغيل الكاميرا المباشرة على هذا الجهاز.',
        );
      });
    return () => {
      cancelled = true;
      stopStream();
    };
  }, [open, stopStream]);

  // Keep the guide sized to the preview.
  useEffect(() => {
    if (!open) return;
    const stage = stageRef.current;
    if (!stage) return;
    const measure = () => setGuide(guideRect(stage.clientWidth, stage.clientHeight, orientation));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [open, orientation]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);

  function close() {
    setPreview(null);
    stopStream();
    onClose();
  }

  function capture() {
    const video = videoRef.current;
    const stage = stageRef.current;
    if (!video || !stage || !guide || !video.videoWidth) return;
    const crop = guideToVideoRect(guide, stage.clientWidth, stage.clientHeight, video.videoWidth, video.videoHeight);
    const size = outputSize(crop);
    const canvas = document.createElement('canvas');
    canvas.width = size.w;
    canvas.height = size.h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, crop.x, crop.y, crop.w, crop.h, 0, 0, size.w, size.h);
    canvas.toBlob(
      blob => {
        if (!blob) return;
        const file = new File([blob], `${fileName}-${Date.now()}.jpg`, { type: 'image/jpeg' });
        setPreview({ file, url: URL.createObjectURL(blob) });
      },
      'image/jpeg',
      0.92,
    );
  }

  function accept() {
    if (!preview) return;
    const file = preview.file;
    setPreview(null);
    stopStream();
    onCapture(file);
  }

  if (!open) return null;

  return (
    <div className="camera-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="camera-panel">
        <div className="camera-head">
          <strong>{title}</strong>
          <button type="button" className="camera-close" onClick={close} aria-label="إغلاق">×</button>
        </div>

        <div className="camera-stage" ref={stageRef}>
          <video
            ref={videoRef}
            className="camera-video"
            autoPlay
            playsInline
            muted
            onLoadedMetadata={() => setReady(true)}
            hidden={!!preview}
          />
          {preview && <img className="camera-preview" src={preview.url} alt="معاينة الصورة الملتقطة" />}

          {!preview && guide && !error && (
            <div
              className="camera-guide"
              style={{ left: guide.x, top: guide.y, width: guide.w, height: guide.h }}
              aria-hidden="true"
            >
              <span className="corner tl" /><span className="corner tr" />
              <span className="corner bl" /><span className="corner br" />
            </div>
          )}

          {!preview && !error && (
            <p className="camera-hint">{ready ? 'ضع الكرت داخل المستطيل ثم اضغط التقاط' : 'جارٍ تشغيل الكاميرا...'}</p>
          )}

          {error && (
            <div className="camera-error">
              <p>{error}</p>
              <button type="button" className="file-action" onClick={() => { close(); onFallback(); }}>
                استخدام كاميرا الجهاز
              </button>
            </div>
          )}
        </div>

        <div className="camera-actions">
          {preview ? (
            <>
              <button type="button" className="btn-gold" onClick={accept}>اعتماد الصورة</button>
              <button type="button" className="file-action secondary" onClick={() => setPreview(null)}>إعادة التصوير</button>
            </>
          ) : (
            <>
              <button type="button" className="btn-gold" onClick={capture} disabled={!ready || !!error}>التقاط</button>
              <button
                type="button"
                className="file-action secondary"
                disabled={!!error}
                onClick={() => setOrientation(o => (o === 'landscape' ? 'portrait' : 'landscape'))}
              >
                {orientation === 'landscape' ? 'كرت عمودي' : 'كرت أفقي'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
