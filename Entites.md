

# Gold

## Company
- Id: GUID
- Name: String
- BusinessSector: String
- CompanyType: Enum (Enterprise, Startup, SME)
- Country: String
- City: String
- Address: String
- PhoneNumber: String
- Email: String
- TeamCompositionSignal: Enum (Unknown, LikelyNo, LikelyYes)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## CompanySignal
- Id: GUID
- CompanyId: GUID
- SignalType: Enum (Funding, Hiring, ProgramMilestone, Expansion, Leadership, Other)
- Source: String
- SourceUrl: String
- Stage: String (nullable)
- Description: String
- OccurredOn: DateTimeOffset
- IngestedOn: DateTimeOffset

## Employee
- Id: GUID
- CompanyId: GUID
- Name: String
- Position: String
- PhoneNumber: String
- Notes: String
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## Match
- Id: GUID
- UserId: GUID
- CompanyId: GUID
- Status: Enum (New, Contacted, Responded, Dismissed, Converted)
- Notes: String
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## MatchScore
- Id: GUID
- MatchId: GUID
- ScoringAlgorithm: Enum
- Score: Integer
- FeatureBreakdown: JSON
- ScoredOn: DateTimeOffset

## MatchFeedback
- Id: GUID
- MatchId: GUID
- Rating: Enum (Positive, Negative)
- GivenOn: DateTimeOffset

## Activity
- Id: GUID
- MatchId: GUID
- EmployeeId: GUID (nullable)
- Type: Enum (Note, EmailSent, CallMade, FollowUpPlanned, ...)
- DueOn: DateTimeOffset (nullable)
- CompletedOn: DateTimeOffset (nullable)
- Notes: String
- OccurredOn: DateTimeOffset
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## Communication
- Id: GUID
- MatchId: GUID
- Channel: Enum (Email, LinkedIn, Other)
- Subject: String (nullable)
- Status: Enum (Drafting, Finalized, Sent)
- CreatedOn: DateTimeOffset
- UpdatedOn: DateTimeOffset

## CommunicationVersion
- Id: GUID
- CommunicationId: GUID
- VersionNumber: Integer
- Content: String
- IsFinal: Boolean
- CreatedOn: DateTimeOffset

## CommunicationRevision
- Id: GUID
- CommunicationVersionId: GUID
- DerivedFromVersionId: GUID (nullable)
- AgentType: Enum (User, AI)
- ChangeSummary: String
- OccurredOn: DateTimeOffset

## CommunicationTurn
- Id: GUID
- CommunicationRevisionId: GUID
- Role: Enum (User, Assistant)
- Content: String
- CreatedOn: DateTimeOffset




# Silver 















Bronze 

