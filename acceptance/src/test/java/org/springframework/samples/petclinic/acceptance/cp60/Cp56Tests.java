package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp56 member-id, UPDATED by cp60: memberId (rederived with the V2 tag) moves under the nested
 *  'identity' object and is gone from the top level. */
@Tag("cp56")
class Cp56Tests extends AcceptanceBase {

	@Test
	void coreMemberIdUnderIdentity() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.identity.memberId").isNotEmpty())
				.andExpect(jsonPath("$.memberId").doesNotExist());
	}
}
