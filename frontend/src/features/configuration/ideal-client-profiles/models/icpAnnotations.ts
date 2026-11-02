// Notes a composing level can show beside the ICP form; their sources live in other features.
export type IcpClientAnnotation = {
  name: string;
  idealExample: boolean;
  industry: string;
  stage: string;
  size: string;
  location: string;
};

export type IcpFeedbackAnnotation = {
  matchId: string;
  companyName: string;
  kind: 'up' | 'down';
  reasonLabel: string | null;
  note?: string | undefined;
};
