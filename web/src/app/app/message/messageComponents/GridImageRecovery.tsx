"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Button } from "@opal/components";
import {
  SvgDownload,
  SvgExternalLink,
  SvgImage,
  SvgRefreshCw,
} from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import { useUser } from "@/providers/UserProvider";
import useGridImageRequests from "@/hooks/useGridImageRequests";
import { recoverImageRequest } from "@/lib/grid/imageRecovery";
import { GridImageReceipt } from "@/lib/grid/interfaces";

interface GridImageRecoveryProps {
  messageId?: number;
  isGenerating?: boolean;
  displayedImageCount?: number;
  showUnavailable?: boolean;
}

export default function GridImageRecovery({
  messageId,
  isGenerating = false,
  displayedImageCount = 0,
  showUnavailable = false,
}: GridImageRecoveryProps) {
  const { user } = useUser();
  const userId = user && !user.is_anonymous_user ? user.id : undefined;
  const anchor = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!anchor.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setVisible(Boolean(entry?.isIntersecting));
      },
      { rootMargin: "200px" }
    );
    observer.observe(anchor.current);
    return () => observer.disconnect();
  }, []);
  const { data, error, isLoading, mutate } = useGridImageRequests(
    messageId,
    userId,
    visible,
    isGenerating
  );
  const allDisplayed =
    data &&
    data.length <= displayedImageCount &&
    data.every((receipt) => receipt.state === "completed");

  return (
    <div ref={anchor} className="min-w-0">
      {userId && data && data.length > 0 && allDisplayed && (
        <Button
          icon={SvgImage}
          prominence="tertiary"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          Original images
        </Button>
      )}
      {userId && data && data.length > 0 && (!allDisplayed || expanded) && (
        <section
          aria-label="Image requests"
          className="flex min-w-0 flex-col gap-3 py-3"
        >
          <Text mainUiAction>Image requests</Text>
          <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2">
            {data.map((receipt, index) => (
              <ImageReceipt
                key={`${userId}:${receipt.request_id}`}
                receipt={receipt}
                userId={userId}
                index={index}
              />
            ))}
          </div>
        </section>
      )}
      {userId && error && showUnavailable && (
        <div role="status" className="flex flex-wrap items-center gap-2 py-2">
          <Text secondaryBody>Image recovery is temporarily unavailable.</Text>
          <Button
            icon={SvgRefreshCw}
            tooltip="Check original image requests"
            onClick={() => void mutate()}
            disabled={isLoading}
          />
        </div>
      )}
    </div>
  );
}

interface ImageReceiptProps {
  receipt: GridImageReceipt;
  userId: string;
  index: number;
}

function ImageReceipt({ receipt, userId, index }: ImageReceiptProps) {
  const url = `/api/grid/images/${receipt.request_id}`;
  const { data, error, isValidating, mutate } = useSWR(
    [url, userId],
    ([endpoint]: [string, string]) => recoverImageRequest(endpoint),
    {
      fallbackData: receipt,
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );
  const [imageError, setImageError] = useState(false);
  const [imageRevision, setImageRevision] = useState(0);
  const current = data ?? receipt;
  const contentURL = `${url}/content`;

  return (
    <div
      className="flex min-w-0 flex-col gap-2"
      data-testid="grid-image-receipt"
    >
      <Text secondaryBody className="break-words">
        Image {index + 1}
        {current.result ? ` · ${current.result.model}` : ""}
      </Text>
      {current.state === "completed" && (
        <>
          {!imageError && (
            <a
              href={contentURL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Open original image ${index + 1}`}
            >
              <img
                src={`${contentURL}?revision=${imageRevision}`}
                alt={`Recovered image ${index + 1}`}
                className="aspect-square w-full rounded-8 object-contain"
                loading="lazy"
                onError={() => setImageError(true)}
              />
            </a>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              icon={SvgExternalLink}
              href={contentURL}
              target="_blank"
              rel="noopener noreferrer"
              tooltip="Open original image"
            />
            <Button
              icon={SvgDownload}
              href={`${contentURL}?download=true`}
              tooltip="Download original image"
            />
          </div>
        </>
      )}
      {current.state === "closed" && (
        <Text secondaryBody>No image was saved for this request.</Text>
      )}
      {current.state === "unconfirmed" && (
        <Text secondaryBody>
          Image status is unconfirmed. No new generation was submitted.
        </Text>
      )}
      {(error || imageError) && (
        <Text secondaryBody role="status">
          The original image is temporarily unavailable.
        </Text>
      )}
      {(current.state === "unconfirmed" || error || imageError) && (
        <Button
          icon={SvgRefreshCw}
          disabled={isValidating}
          onClick={() => {
            setImageError(false);
            setImageRevision((revision) => revision + 1);
            void mutate();
          }}
        >
          Check original image
        </Button>
      )}
    </div>
  );
}
