package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

/** cp55 owner-segment: Return 'ownerSegment' derived from membershipLevel, locality and household size via a rule... */
@Tag("cp55")
class Cp55Tests extends AcceptanceBase {

	@Test
	void coreReturnsOwnerSegment() throws Exception {
		int id = createOwnerOk(structuredOwner());
		getOwner(id).andExpect(jsonPath("$.ownerSegment").exists());
	}
}
