import type { components } from '../../../../api/generated/schema';

export type AccountResponse = components['schemas']['UserResponse'];
export type AccountDraft = {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  country_of_residence: string;
  timezone: string;
};

export function createAccountDraft(account: AccountResponse): AccountDraft {
  return {
    first_name: account.first_name,
    last_name: account.last_name,
    email: account.email,
    phone_number: account.phone_number,
    country_of_residence: account.country_of_residence,
    timezone: account.timezone ?? '',
  };
}
