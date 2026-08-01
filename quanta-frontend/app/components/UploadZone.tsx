"use client";

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import { UploadCloud } from "lucide-react";

import { cn } from "@/lib/utils";

const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".dta", ".sav"] as const;

type AcceptedExtension = (typeof ACCEPTED_EXTENSIONS)[number];

const BORDER_REST = "rgba(255, 255, 255, 0.06)";
const BORDER_ACTIVE = "#C9A84C";
const SHADOW_REST = "0 0 0px transparent";
const SHADOW_ACTIVE = "0 0 40px rgba(201, 168, 76, 0.08)";

const MOTION_TRANSITION = {
  duration: 0.3,
  ease: [0.4, 0, 0.2, 1] as const,
};

export interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  selectedFile?: File | null;
}

function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot === -1) {
    return "";
  }
  return filename.slice(lastDot).toLowerCase();
}

function isAcceptedExtension(ext: string): ext is AcceptedExtension {
  return (ACCEPTED_EXTENSIONS as readonly string[]).includes(ext);
}

function isValidFile(file: File): boolean {
  return isAcceptedExtension(getFileExtension(file.name));
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} o`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} Ko`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export function UploadZone({ onFileSelect, selectedFile = null }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);

  const [isDragging, setIsDragging] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isActive = isDragging || isHovered;

  const processFile = useCallback(
    (file: File) => {
      if (!isValidFile(file)) {
        setError(
          "Format non pris en charge. Utilisez CSV, XLSX, DTA ou SAV.",
        );
        return;
      }

      setError(null);
      onFileSelect(file);
    },
    [onFileSelect],
  );

  const openFilePicker = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current += 1;
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      dragCounterRef.current = 0;
      setIsDragging(false);

      const file = event.dataTransfer.files[0];
      if (file) {
        processFile(file);
      }
    },
    [processFile],
  );

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) {
        processFile(file);
      }
      event.target.value = "";
    },
    [processFile],
  );

  return (
    <div className="w-full">
      <motion.div
        role="button"
        tabIndex={0}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-hero bg-quanta-surface px-8 py-12",
          isActive ? "border border-solid" : "border border-dashed",
        )}
        animate={{
          borderColor: isActive ? BORDER_ACTIVE : BORDER_REST,
          boxShadow: isActive ? SHADOW_ACTIVE : SHADOW_REST,
        }}
        transition={MOTION_TRANSITION}
        onClick={openFilePicker}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openFilePicker();
          }
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.dta,.sav"
          className="hidden"
          onChange={handleInputChange}
        />

        <UploadCloud
          className={cn(
            "size-10 transition-colors duration-300",
            isActive ? "text-quanta-gold" : "text-quanta-muted",
          )}
          strokeWidth={1.5}
          aria-hidden
        />

        {selectedFile ? (
          <div className="flex flex-col items-center gap-1 text-center">
            <p className="font-sans text-quanta-primary text-sm">
              {selectedFile.name}
            </p>
            <p className="font-sans text-quanta-muted text-xs">
              {formatFileSize(selectedFile.size)}
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1 text-center">
            <p className="font-display text-lg font-light text-quanta-primary">
              Déposez votre base de données
            </p>
            <p className="font-sans text-sm text-quanta-muted">
              CSV, Excel, Stata, SPSS — jusqu&apos;à 10 Mo
            </p>
            <p className="font-sans text-xs text-quanta-muted">
              ou cliquez pour parcourir
            </p>
          </div>
        )}
      </motion.div>

      {error ? (
        <p className="mt-2 font-sans text-sm text-quanta-error">{error}</p>
      ) : null}
    </div>
  );
}
