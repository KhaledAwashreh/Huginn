import { ref } from 'vue';

export type Leader = { name: string; role: string; bio: string };
export type ClientReference = {
  name: string;
  role: string;
  startMonth: string;
  endMonth: string;
  current: boolean;
  work: string;
  industry: string;
  stage: string;
  size: string;
  location: string;
  idealExample: boolean;
};
export type ProfileResource = { id: string; title: string; url: string };
export type BusinessDetails = {
  name: string;
  tagline: string;
  website: string;
  location: string;
  practice: string;
  leaders: Leader[];
  clients: ClientReference[];
  resources: ProfileResource[];
};

const empty = (): BusinessDetails => ({
  name: '',
  tagline: '',
  website: '',
  location: '',
  practice: '',
  leaders: [],
  clients: [],
  resources: [],
});

// No API stores this business data yet, so it is held in memory and never persisted.
export function useBusinessDetails() {
  const details = ref<BusinessDetails>(empty());

  function saveDetails(changes: Partial<BusinessDetails>): void {
    details.value = { ...details.value, ...changes };
  }

  return { details, saveDetails };
}
