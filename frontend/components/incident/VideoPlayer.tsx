"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import ReactPlayer from "react-player/lazy";

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

interface VideoPlayerProps {
  src: string;
  onDuration?: (seconds: number) => void;
}

/**
 * Video player (react-player) exposing imperative seekTo() so the timeline and
 * reasoning graph can jump to a moment.
 */
export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ src, onDuration }, ref) => {
    const playerRef = useRef<ReactPlayer>(null);

    useImperativeHandle(ref, () => ({
      seekTo: (seconds: number) => playerRef.current?.seekTo(seconds, "seconds"),
    }));

    return (
      <div className="aspect-video w-full overflow-hidden rounded-lg border bg-black">
        {src ? (
          <ReactPlayer
            ref={playerRef}
            url={src}
            controls
            width="100%"
            height="100%"
            onDuration={onDuration}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
            Видео недоступно для воспроизведения.
          </div>
        )}
      </div>
    );
  }
);
VideoPlayer.displayName = "VideoPlayer";
