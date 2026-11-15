"""DOC-001 Information Security Policy, part 2: sections 8 to 11 (data and access controls)."""

from app.datagen import model as m
from app.datagen.facts import Facts
from app.datagen.markup import section


def sections(facts: Facts, entry) -> tuple[m.Section, ...]:
    return (
        _assets(),
        _access(facts),
        _cryptography(facts),
        _privacy(facts),
    )


def _assets() -> m.Section:
    return section(
        "8. Asset management and data classification",
        """
        The company cannot protect what it has not identified. This section requires every asset
        to be recorded, owned and classified, and it sets the handling rules that follow from the
        classification.

        ### 8.1 Asset inventory

        Every information asset, system, application and device that stores or processes company
        or customer data must be recorded in the asset inventory. Each entry names an owner, a
        classification, a location and a business purpose. The inventory is updated when an asset
        is acquired, changed or retired, and the security team reconciles it against discovery
        tools twice a year to find assets that were never recorded.

        ### 8.2 Classification scheme

        Information is classified by the harm that would follow if it were disclosed, altered or
        lost. The owner of the information chooses the level when it is created, and any person
        who handles it must follow the rules for that level.

        | Level | Meaning | Examples | Who may access |
        |---|---|---|---|
        | Public | Approved for release outside the company | Published certificates, the
          support policy, marketing material | Anyone |
        | Internal | For use by personnel in the course of their work | Policies, procedures,
          staff handbook, internal announcements | All personnel |
        | Confidential | Sensitive business or technical information | Architecture designs,
          test reports, supplier contracts | Named roles with a business need |
        | Restricted | The most sensitive information, whose disclosure would cause serious
          harm | Financial results, strategic plans, salary data, encryption keys | Named
          individuals only |
        Caption: Table 7. Classification levels

        Information that has no label is treated as Internal until its owner decides otherwise.
        When a document combines information of several levels, the highest level applies to
        the whole document.

        ### 8.3 Labelling and handling

        The classification of a document must be visible on its first page or in its header.
        The following rules apply to everyone who handles classified information.

        - Public information may be shared freely once the owner has approved its release.
        - Internal information may be shared inside the company but not posted publicly or sent
        to people outside it without a business reason and an agreement that covers its use.
        - Confidential information may be stored only in approved systems, shared only with
        people whose role requires it, and sent outside the company only over encrypted
        channels under a signed confidentiality agreement.
        - Restricted information is held in locations that enforce named access, is never copied
        to personal devices or personal accounts, and every access to it is logged.

        ### 8.4 Media, devices and disposal

        Removable media may not be used to store Confidential or Restricted information unless
        the media is encrypted and the owner has approved its use. Laptops must use full-disk
        encryption and a screen lock. When a device or storage medium reaches the end of its
        life, the Head of IT Operations arranges secure erasure or physical destruction, records
        the date and method, and keeps the certificate of destruction where a supplier provides
        one.

        ### 8.5 Evidence

        The asset inventory, the classification labels on documents, the records of the
        reconciliation done twice a year and the disposal records show that this section is
        being followed.
        """,
    )


def _access(facts: Facts) -> m.Section:
    min_length = facts.get("security.password_min_length")
    return section(
        "9. Identity and access management",
        f"""
        Access control decides who can reach which information and systems. The rules in this
        section apply to personnel and to the automated accounts that act on their behalf.

        ### 9.1 Account lifecycle

        Access follows the working life of the person. When someone joins, the line manager
        requests the access their role needs, and the system owner approves it. When someone
        changes role, access that is no longer needed is removed at the same time as new access
        is added. When someone leaves, the Head of People notifies IT Operations in advance, and
        all of the person's access is removed on or before the last working day. Accounts that
        have not been used for 90 days are disabled automatically.

        ### 9.2 Authentication

        Every person must have a unique account. Shared accounts are not permitted for people,
        and credentials must never be shared, written down in plain sight or stored in code.

        Multi-factor authentication is required for all staff on every company system that
        supports it, including email, the source code repositories, the production
        environment and the administrative interfaces of the platform. This rule applies to
        every employee, contractor and intern, not only to administrators. A person who has
        not enrolled in multi-factor authentication does not receive access.

        Passwords must be at least {min_length} characters long. The identity service rejects
        passwords that appear in lists of known breached passwords, that repeat a previous
        password, or that contain the person's name or account name. People are encouraged to
        use the company password manager so that each system has a different, random
        password. Accounts are locked temporarily after repeated failed sign-in attempts, and
        the lock is reported to the security team.

        ### 9.3 Authorisation and least privilege

        Access is granted through roles that match job duties. System owners define the roles
        for their systems and approve every request against them. A request that goes beyond
        the role requires a written reason and the approval of both the system owner and the
        person's line manager.

        | Access type | Approver | Review frequency |
        |---|---|---|
        | Standard access to internal systems | Line manager | Every six months |
        | Access to source code and build systems | Head of Engineering | Every six months |
        | Access to production systems | Head of IT Operations | Every quarter |
        | Privileged and administrator access | Chief Information Security Officer | Every
          quarter |
        | Access to Restricted information | Information owner | Every quarter |
        Caption: Table 8. Access approval and review

        ### 9.4 Privileged access

        Administrators use a separate account for administrative work and never use it for
        email or browsing. Privileged access to production is granted for a defined task and
        period where tooling allows, and every privileged session is logged. Emergency access
        that bypasses normal approval is allowed only during an incident, is recorded by the
        incident commander, and is reviewed within five working days.

        ### 9.5 Access reviews

        System owners review who has access to their systems at the frequency shown in table 8.
        The reviewer confirms each account is still needed and that the level of access is
        right. Access that is not confirmed is removed. Review results, including any access
        that was removed, are kept as evidence.

        ### 9.6 Remote access and devices

        Staff reach company systems only from managed devices or from devices that meet the
        minimum security configuration. Remote connections to internal networks use an
        encrypted tunnel with multi-factor authentication. Lost or stolen devices must be
        reported to the security team at once so that access can be revoked and, where
        possible, the device wiped.

        ### 9.7 Evidence

        Evidence for this section includes joiner, mover and leaver tickets, multi-factor
        enrolment reports from the identity service, password policy settings, access review
        records, and the logs of privileged sessions.
        """,
    )


def _cryptography(facts: Facts) -> m.Section:
    at_rest = facts.get("security.encryption_at_rest")
    in_transit = facts.get("security.encryption_in_transit")
    mode = facts.get("architecture.encryption.mode")
    rotation = facts.get("security.key_rotation_days")
    return section(
        "10. Cryptography and key management",
        f"""
        Encryption is the control that keeps customer data unreadable if every other control
        fails. This section sets what must be encrypted, with which standards, and how keys are
        looked after.

        ### 10.1 Principles

        The company uses well-established, publicly reviewed algorithms and the cryptographic
        libraries of reputable vendors. Staff must not design their own algorithms or
        protocols. Cryptographic choices are reviewed by the security team before they are
        used for customer data, and they are reviewed again when the industry changes its
        guidance.

        ### 10.2 Data at rest

        Customer data stored by the platform is encrypted at rest using {at_rest} in {mode} mode.
        This covers primary databases, read replicas, object storage, search indexes and
        backups. Laptops and other end-user devices use full-disk encryption. Encryption at rest
        is enabled by default, and an engineer cannot create a data store for customer data
        without it.

        ### 10.3 Data in transit

        All connections to the platform from customers' browsers and integrations must use
        {in_transit}. Traffic between the platform's internal services is also encrypted in
        transit. Connections that cannot use the required protocol are refused rather than
        downgraded. Email that carries Confidential information is sent only over encrypted
        channels.

        ### 10.4 Key management

        Keys are managed by a dedicated key service using envelope encryption, in which data is
        encrypted with data keys and the data keys are themselves encrypted with master keys.
        The following rules apply to every key that protects customer data.

        - Keys are generated inside the key service from a strong source of randomness.
        - Master keys never leave the key service in unencrypted form.
        - Keys are rotated at least every {rotation} days, and immediately when compromise is
        suspected or when a person with access to key material leaves the company.
        - Access to administer keys is limited to a small named group, uses multi-factor
        authentication, and every action is logged.
        - Old keys are retained only as long as needed to decrypt data that has not yet been
        re-encrypted, and are then destroyed with a recorded date.

        ### 10.5 Certificates and secrets

        The security team maintains an inventory of the certificates the company uses and
        monitors their expiry dates so that none lapses unnoticed. Application secrets such as
        tokens, passwords and connection strings are stored in a secrets manager. They must not
        appear in source code, in tickets or in chat messages, and automated scanning blocks
        code that contains them.

        | Data state | Requirement | Owner |
        |---|---|---|
        | Customer data at rest | {at_rest}, {mode} mode | Head of IT Operations |
        | Customer data in transit | {in_transit} | Head of Engineering |
        | Encryption keys | Envelope encryption, rotated every {rotation} days |
          Information Security Manager |
        | Backups | Encrypted with the same standard as the data they protect | Head of IT
          Operations |
        | Secrets and credentials | Held in the secrets manager, never in code | Head of
          Engineering |
        Caption: Table 9. Cryptographic requirements

        ### 10.6 Evidence

        Evidence includes the configuration of the data stores and load balancers, the key
        service rotation logs, the certificate inventory, and the results of the scans that look
        for secrets in code.
        """,
    )


def _privacy(facts: Facts) -> m.Section:
    regions = " and ".join(facts.get("security.data_residency"))
    deletion = facts.get("privacy.customer_data_deletion_days")
    logs = facts.get("security.log_retention_days")
    return section(
        "11. Data residency, privacy and retention",
        f"""
        Customers choose where their data lives, and they expect the company to honour that
        choice and to handle personal data lawfully. This section describes how the company
        meets those expectations.

        ### 11.1 Data residency

        Customer data is hosted in {regions}. The customer selects a region when its account
        is created, and the platform keeps that customer's data, its backups and the logs that
        contain it in the selected region. Customer data must not be copied or moved to a
        different region, or to a development or test environment, unless the customer has
        instructed the company to do so in writing and the Head of Legal and Compliance has
        approved the transfer.

        ### 11.2 Privacy obligations

        For personal data in customer content, the company acts as a processor on behalf of
        the customer and follows the customer's documented instructions. The company maintains
        a privacy policy that addresses the requirements of India's Digital Personal Data
        Protection Act, and it makes a data processing agreement based on the European Union's
        General Data Protection Regulation available to customers who need one. The Data
        Protection Officer is the contact point for privacy questions and for regulators.

        ### 11.3 Data minimisation and access

        The company collects only the personal data it needs to deliver the service, and it
        does not use customer data for purposes that the customer has not agreed. Support staff
        may view customer data only when a customer request or an incident requires it, and
        each such access is logged and linked to the ticket that justified it.

        ### 11.4 Retention and deletion

        Records are kept for as long as they are needed for the purpose they were collected
        for, and no longer. When a customer asks for its data to be deleted, or its contract
        ends, the company deletes the customer's data within {deletion} days. Backups that hold
        the deleted data are overwritten by the normal backup cycle and are never restored for
        a purpose other than disaster recovery.

        | Record | Retention | Reason |
        |---|---|---|
        | Customer data | Until the customer asks for deletion or the contract ends, then deleted
          within {deletion} days | Contract and customer instruction |
        | Security and audit logs | {logs} days | Investigation, audit and customer assurance |
        | Access review and approval records | Three years | Audit evidence |
        | Incident records | Five years | Learning, audit and legal defence |
        | Training records | Duration of employment plus two years | Compliance evidence |
        Caption: Table 10. Retention periods

        ### 11.5 Evidence

        Evidence includes the region setting for each customer account, the data processing
        agreements in place, deletion requests and the dates on which they were completed, and
        the retention settings of the log and backup systems.
        """,
    )
