package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** identity-v2: apiVersion is 2, the memberId/identityKey/householdId are grouped under a nested
 * 'identity' object, and those three are no longer at the top level. Exact structural contract. */
@Tag("cp60")
class Cp60Tests extends AcceptanceBase {

	@Test
	void coreV2GroupsIdentityAndVersions() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.apiVersion").value(2))
				.andExpect(jsonPath("$.identity.memberId").isNotEmpty())
				.andExpect(jsonPath("$.identity.identityKey").isNotEmpty())
				.andExpect(jsonPath("$.identity.householdId").isNotEmpty())
				.andExpect(jsonPath("$.memberId").doesNotExist())
				.andExpect(jsonPath("$.identityKey").doesNotExist())
				.andExpect(jsonPath("$.householdId").doesNotExist());
	}
}
